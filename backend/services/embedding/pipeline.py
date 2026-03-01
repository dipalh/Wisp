"""
Embedding pipeline — 3-layer smart ingestion (Cowork-style).

Architecture
------------
  Layer A — FILE CARD (every file, always):
      Rich metadata record: path, size, type, folder context, filename
      tokens, optional local peek.  Guarantees every file is findable
      by name, type, or location.  No Gemini API calls.

  Layer B — AI PREVIEW (bounded Gemini, targeted):
      Images/screenshots → Gemini vision caption + keywords (~100 tokens)
      PDFs/office (with text) → Gemini summary of extracted text (~150 tokens)
      Scanned PDFs (no text) → Gemini document understanding (~150 tokens)
      Produces a semantic layer that makes files meaningfully searchable
      without full-content ingestion.

  Layer C — DEEPENING (on-demand, top hits only):
      When a query hits card-only or preview-only files, auto-extract
      and embed full content (via Gemini dispatcher) for those few files.
      This is the "gets smarter right when you care" moment.

Depth levels
------------
  "card"    — Layer A only: metadata card embedded (video, audio, archives, exe)
  "preview" — Layer A+B: card + AI caption/summary (images, scanned PDFs)
  "deep"    — Full: card + all content chunked + embedded (text, code, PDFs, office)
              PDFs/office at "deep" also get an AI summary in their card.

Public API
----------
  ingest(result, file_id)          — Low-level: ContentResult → store
  ingest_file(file_path, file_id)  — Smart 3-layer: classify → extract → AI → store
  deepen_file(file_path, file_id)  — Force full extraction via Gemini dispatcher
  search(query, k)                 — Semantic search with diversity filter
  ask(query, k)                    — RAG with auto-deepening of top hits
  delete_file(file_id)             — Remove a file's chunks from store
  scan_summary()                   — Coverage report after bulk ingestion
  init_store(db_path)              — Initialise vector store + cache
  teardown_store()                 — Close store + save cache
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ai.embed import embed_batch, embed_text
from ai.generate import generate_text, generate_with_file
from services.embedding.chunker import Chunk, chunk_text
from services.embedding import store

# ── Concurrency guards ────────────────────────────────────────────────────────
# Per-process safety belts.  Under Celery, the REAL global throttle is
# worker concurrency + dedicated queues (queue="ai" concurrency=2,
# queue="embed" concurrency=4).  These semaphores prevent a single
# async process from over-saturating threads / the embedding endpoint.
_EMBED_SEM = asyncio.Semaphore(8)   # max concurrent embedding thread-pool calls
_AI_SEM    = asyncio.Semaphore(4)   # max concurrent Gemini API calls
from services.embedding.store import SearchHit
from services.file_processor.models import ContentResult


# ── Optional local PDF extraction ─────────────────────────────────────────────

try:
    from pypdf import PdfReader as _PdfReader
    _HAS_PYPDF = True
except ImportError:
    _HAS_PYPDF = False


# ── Ingest policy constants ──────────────────────────────────────────────────

MAX_EMBED_CHARS        = 30_000     # Hard cap on chars to embed per file
MAX_CHUNKS_PER_FILE    = 12         # Hard cap on chunks after chunking
PREVIEW_CHARS          = 500        # Content peek for file cards
AI_PREVIEW_INPUT_CHARS = 10_000     # Max chars sent to Gemini for summary
MAX_PDF_PAGES_EMBED    = 80         # PDFs above this → ai_preview not full
MAX_IMAGE_SIZE_CAPTION = 20_000_000 # 20 MB — skip vision for huge images
MAX_PDF_SIZE_FOR_AI    = 10_000_000 # 10 MB — skip Gemini PDF vision for huge PDFs
CHUNK_SIZE             = 800        # Characters per chunk
CHUNK_OVERLAP          = 100        # Overlap between chunks


# ── Extension sets ────────────────────────────────────────────────────────────

IMAGE_EXTENSIONS = frozenset({
    ".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif", ".gif", ".svg",
    ".ico", ".icns",
})

VIDEO_EXTENSIONS = frozenset({
    ".mp4", ".mov", ".avi", ".webm", ".mkv", ".flv", ".wmv", ".3gp",
    ".mpeg", ".mpg",
})

AUDIO_EXTENSIONS = frozenset({
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".aiff",
})

MEDIA_EXTENSIONS = IMAGE_EXTENSIONS | VIDEO_EXTENSIONS | AUDIO_EXTENSIONS

TEXT_LIKE_EXTENSIONS = frozenset({
    ".txt", ".md", ".html", ".htm", ".css", ".csv", ".xml", ".json",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf", ".log", ".sql",
    ".reg", ".nfo", ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c",
    ".cpp", ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".sh", ".bash",
    ".bat", ".cmd", ".ps1", ".psm1", ".psd1", ".vbs", ".eml", ".ics",
    ".vcf", ".tex", ".sol", ".wl", ".mermaid", ".r", ".lua", ".pl",
    ".zig", ".h", ".hpp", ".m", ".rtf",
})

OFFICE_EXTENSIONS = frozenset({
    ".docx", ".pptx", ".xlsx", ".doc", ".ppt", ".xls",
    ".odt", ".odp", ".ods",
})

ARCHIVE_EXTENSIONS = frozenset({
    ".zip", ".7z", ".tar", ".tgz", ".gz", ".bz2", ".xz", ".rar",
})

EXECUTABLE_EXTENSIONS = frozenset({
    ".exe", ".dll", ".msi",
})

# Extensions eligible for auto-deepening in ask().
# Archives, audio, video, and executables are NOT deepened — they produce
# garbage text and waste tokens.
DEEPEN_EXTENSIONS = TEXT_LIKE_EXTENSIONS | {".pdf"} | OFFICE_EXTENSIONS | IMAGE_EXTENSIONS


# ── MIME type map for Gemini vision ──────────────────────────────────────────

_IMAGE_MIME: dict[str, str] = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif",
    ".gif": "image/gif", ".svg": "image/svg+xml", ".ico": "image/x-icon",
    ".icns": "image/x-icns",
}


# ── Human-readable type descriptions ─────────────────────────────────────────

_TYPE_MAP: dict[str, str] = {
    ".pdf": "PDF document", ".docx": "Word document",
    ".xlsx": "Excel spreadsheet", ".pptx": "PowerPoint presentation",
    ".doc": "Word document (legacy)", ".xls": "Excel spreadsheet (legacy)",
    ".ppt": "PowerPoint (legacy)", ".odt": "OpenDocument Text",
    ".ods": "OpenDocument Spreadsheet", ".odp": "OpenDocument Presentation",
    ".png": "PNG image", ".jpg": "JPEG image", ".jpeg": "JPEG image",
    ".gif": "GIF image", ".svg": "SVG vector image", ".webp": "WebP image",
    ".heic": "HEIC image", ".heif": "HEIF image", ".ico": "icon file",
    ".icns": "macOS icon", ".mp4": "MP4 video", ".mov": "QuickTime video",
    ".avi": "AVI video", ".webm": "WebM video", ".mkv": "MKV video",
    ".mp3": "MP3 audio", ".wav": "WAV audio", ".m4a": "M4A audio",
    ".flac": "FLAC audio", ".aac": "AAC audio", ".ogg": "OGG audio",
    ".zip": "ZIP archive", ".tar": "TAR archive", ".gz": "gzip file",
    ".7z": "7-Zip archive", ".rar": "RAR archive",
    ".dmg": "macOS disk image", ".exe": "Windows executable",
    ".msi": "Windows installer", ".pkg": "macOS installer package",
    ".dll": "Windows dynamic library",
    ".py": "Python code", ".js": "JavaScript code", ".ts": "TypeScript code",
    ".tsx": "TypeScript React", ".jsx": "JavaScript React",
    ".java": "Java code", ".c": "C code", ".cpp": "C++ code",
    ".go": "Go code", ".rs": "Rust code", ".rb": "Ruby code",
    ".html": "HTML document", ".htm": "HTML document",
    ".css": "CSS stylesheet", ".json": "JSON data", ".csv": "CSV data",
    ".xml": "XML document", ".yaml": "YAML config", ".yml": "YAML config",
    ".md": "Markdown document", ".txt": "text file", ".log": "log file",
    ".sql": "SQL script", ".sh": "shell script", ".bash": "bash script",
}


# ── Result types ─────────────────────────────────────────────────────────────


@dataclass
class IngestResult:
    file_id: str
    file_path: str
    chunk_count: int
    skipped: bool = False          # True when cached / nothing to embed
    depth: str = "deep"            # "card" | "preview" | "deep"
    engine: str = ""               # extraction engine used
    errors: list[str] = field(default_factory=list)


@dataclass
class AskResult:
    """Structured result from the RAG ``ask()`` function."""
    answer: str
    hits: list[SearchHit]
    query: str
    deepened_files: list[str] = field(default_factory=list)


# ── File classification ──────────────────────────────────────────────────────


def classify_file(
    ext: str,
    file_size: int = 0,
    pdf_pages: int | None = None,
) -> str:
    """Return ``'full'``, ``'ai_preview'``, or ``'card_only'``.

    Strategy:
      text/code      → ``'full'``        local extraction, full chunking, no AI needed
      PDF ≤ 80 pages → ``'full'``        local pypdf + AI summary in card
      PDF > 80 pages → ``'ai_preview'``  AI summary of first pages, no full chunk
      office         → ``'full'``        local extraction + AI summary
      images ≤ 20 MB → ``'ai_preview'``  Gemini vision caption
      images > 20 MB → ``'card_only'``   too large for vision API
      video/audio    → ``'card_only'``   metadata only
      archives/exe   → ``'card_only'``   metadata only
      unknown        → ``'card_only'``   metadata only
    """
    if ext in TEXT_LIKE_EXTENSIONS:
        return "full"
    if ext == ".pdf":
        if pdf_pages is not None and pdf_pages > MAX_PDF_PAGES_EMBED:
            return "ai_preview"
        return "full"
    if ext in OFFICE_EXTENSIONS:
        return "full"
    if ext in IMAGE_EXTENSIONS:
        if file_size > MAX_IMAGE_SIZE_CAPTION:
            return "card_only"
        return "ai_preview"
    # video, audio, archives, executables, unknown
    return "card_only"


# ── AI preview functions (Layer B) ───────────────────────────────────────────

_CAPTION_PROMPT = (
    "Describe this image in 1-2 concise sentences. "
    "Then list 3-5 keywords separated by commas.\n"
    "Format:\nDescription: <your description>\nKeywords: <keyword1>, <keyword2>, ..."
)

_SUMMARIZE_PROMPT = (
    "Summarize this document excerpt in 3-5 sentences. "
    "Include the title if visible, key topics, and notable details "
    "(names, numbers, dates). Be specific and concise."
)

_PDF_VISION_PROMPT = (
    "Summarize this PDF document in 3-5 sentences. "
    "Describe what the document is about, its title if visible, "
    "and any key information (names, numbers, dates). Be concise."
)


async def _ai_caption_image(file_bytes: bytes, ext: str, filename: str) -> str:
    """Call Gemini vision to produce a 1-2 sentence caption + keywords."""
    mime = _IMAGE_MIME.get(ext, "image/jpeg")
    prompt = f'This file is named "{filename}". {_CAPTION_PROMPT}'
    try:
        text = await generate_with_file(prompt, file_bytes, mime, ext)
        return text.strip()
    except Exception:
        return ""


async def _ai_summarize_text(text: str, filename: str) -> str:
    """Call Gemini to summarize extracted text → 3-5 sentence summary."""
    excerpt = text[:AI_PREVIEW_INPUT_CHARS]
    prompt = (
        f'This is an excerpt from a file named "{filename}":\n\n'
        f'{excerpt}\n\n'
        f'{_SUMMARIZE_PROMPT}'
    )
    try:
        result = await generate_text(prompt)
        return result.strip()
    except Exception:
        return ""


async def _ai_summarize_pdf_vision(file_bytes: bytes, filename: str) -> str:
    """Call Gemini document understanding on a scanned/image-based PDF."""
    if len(file_bytes) > MAX_PDF_SIZE_FOR_AI:
        return ""
    prompt = f'This PDF is named "{filename}". {_PDF_VISION_PROMPT}'
    try:
        text = await generate_with_file(prompt, file_bytes, "application/pdf", ".pdf")
        return text.strip()
    except Exception:
        return ""


# ── Local extraction helpers ─────────────────────────────────────────────────


def _extract_pdf_local(
    file_bytes: bytes,
    max_chars: int = MAX_EMBED_CHARS,
) -> tuple[str, int]:
    """Extract text from a PDF locally using pypdf.  Returns ``(text, total_pages)``."""
    if not _HAS_PYPDF:
        return "", 0
    try:
        reader = _PdfReader(io.BytesIO(file_bytes))
        total_pages = len(reader.pages)

        parts: list[str] = []
        chars = 0
        for page in reader.pages:
            page_text = page.extract_text() or ""
            parts.append(page_text)
            chars += len(page_text)
            if chars >= max_chars:
                break

        text = "\n\n".join(parts)
        return text[:max_chars], total_pages
    except Exception:
        return "", 0


def _pdf_page_count(file_bytes: bytes) -> int:
    """Quick page count without extracting text."""
    if not _HAS_PYPDF:
        return 0
    try:
        return len(_PdfReader(io.BytesIO(file_bytes)).pages)
    except Exception:
        return 0


def _human_size(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} bytes"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    if size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def _extract_for_embed(
    file_path: Path,
    ext: str,
    file_bytes: bytes,
) -> tuple[str, str]:
    """Extract content for embedding (locally, no Gemini).

    Returns ``(text, engine_used)``.  Content is capped at MAX_EMBED_CHARS.
    """
    # Text-like → direct decode
    if ext in TEXT_LIKE_EXTENSIONS:
        try:
            text = file_bytes.decode("utf-8", errors="replace")
            return text[:MAX_EMBED_CHARS], "local"
        except Exception:
            return "", "error"

    # PDF → local extraction via pypdf
    if ext == ".pdf":
        text, pages = _extract_pdf_local(file_bytes, MAX_EMBED_CHARS)
        if text.strip():
            return text, f"local-pdf ({pages}p)"
        return "", "empty-pdf"

    # Office → local extractor
    if ext in OFFICE_EXTENSIONS:
        try:
            from services.file_processor.extractors import office
            text = office.extract(file_bytes, ext)
            return text[:MAX_EMBED_CHARS], "local-office"
        except Exception as e:
            return "", f"office-error: {e}"

    # Archives → local listing
    if ext in ARCHIVE_EXTENSIONS:
        try:
            from services.file_processor.extractors import archive
            text = archive.extract(file_bytes, ext)
            return text[:MAX_EMBED_CHARS], "local-archive"
        except Exception:
            return "", "archive-error"

    # Executables → binary metadata
    if ext in EXECUTABLE_EXTENSIONS:
        try:
            from services.file_processor.extractors import binary
            text = binary.extract(file_bytes, ext)
            return text[:MAX_EMBED_CHARS], "local-binary"
        except Exception:
            return "", "binary-error"

    # Unknown → try UTF-8
    try:
        text = file_bytes.decode("utf-8")
        if text.strip():
            return text[:MAX_EMBED_CHARS], "local-guess"
    except (UnicodeDecodeError, ValueError):
        pass

    return "", "unsupported"


def _category_for_ext(ext: str) -> str:
    if ext in MEDIA_EXTENSIONS:
        return "media"
    if ext in TEXT_LIKE_EXTENSIONS:
        return "text"
    if ext == ".pdf":
        return "document"
    if ext in OFFICE_EXTENSIONS:
        return "office"
    if ext in ARCHIVE_EXTENSIONS:
        return "archive"
    if ext in EXECUTABLE_EXTENSIONS:
        return "binary"
    return "other"


# ── File card builder (Layer A) ──────────────────────────────────────────────


def _filename_tokens(name: str) -> list[str]:
    """Split filename stem into searchable tokens."""
    stem = Path(name).stem
    tokens = re.split(r'[-_\s.()[\]{}]', stem)
    return [t.lower() for t in tokens if t and len(t) > 1]


def _folder_context(file_path: Path) -> str:
    """Parent folder names as location context."""
    parts = file_path.parts[:-1]
    relevant = parts[-3:] if len(parts) > 3 else parts
    return " > ".join(relevant) if relevant else ""


def _make_file_card(
    file_path: Path,
    ext: str,
    file_bytes: bytes | None = None,
    ai_summary: str = "",
) -> str:
    """Build a rich file card for Layer A.

    Includes: metadata, folder context, filename tokens, local content peek,
    and an optional AI-generated summary/caption.
    """
    name = file_path.name
    try:
        size = file_path.stat().st_size
    except OSError:
        size = len(file_bytes) if file_bytes else 0
    size_str = _human_size(size)
    type_desc = _TYPE_MAP.get(ext, f"file ({ext})")
    folder = _folder_context(file_path)
    tokens = _filename_tokens(name)

    # Local content peek
    peek = ""
    if file_bytes:
        if ext in TEXT_LIKE_EXTENSIONS:
            try:
                peek = file_bytes[:PREVIEW_CHARS * 2].decode(
                    "utf-8", errors="replace"
                ).strip()[:PREVIEW_CHARS]
            except Exception:
                pass
        elif ext == ".pdf":
            text, _ = _extract_pdf_local(file_bytes, max_chars=PREVIEW_CHARS)
            peek = text.strip()[:PREVIEW_CHARS]

    lines = [
        f"[FILE CARD] {name}",
        f"Type: {type_desc}  |  Size: {size_str}",
    ]
    if folder:
        lines.append(f"Location: {folder}")
    if tokens:
        lines.append(f"Name tokens: {', '.join(tokens)}")
    if peek:
        lines.append(f"Content preview: {peek}")
    if ai_summary:
        lines.append(f"AI Summary: {ai_summary}")
    if not ai_summary and not peek:
        lines.append(
            f"This {type_desc} named \"{name}\" ({size_str}) is in the user's files."
        )
    return "\n".join(lines)


# ── Fingerprint cache ────────────────────────────────────────────────────────
#
# Simple JSON file stored alongside the LanceDB directory.  Maps file paths
# to their fingerprint + ingestion metadata so unchanged files are skipped.

_cache: dict[str, dict] = {}
_cache_path: Path | None = None


def _init_cache(db_path: str | None = None) -> None:
    global _cache, _cache_path
    path = db_path or store.current_db_path()
    if path:
        _cache_path = Path(path) / "wisp_ingest_cache.json"
        if _cache_path.exists():
            try:
                _cache = json.loads(_cache_path.read_text())
            except Exception:
                _cache = {}
        else:
            _cache = {}
    else:
        _cache = {}
        _cache_path = None


def _save_cache() -> None:
    if _cache_path:
        try:
            _cache_path.write_text(json.dumps(_cache))
        except Exception:
            pass


def _fingerprint(file_path: Path) -> str:
    try:
        stat = file_path.stat()
        return f"{file_path}:{stat.st_size}:{stat.st_mtime_ns}"
    except OSError:
        return ""


def _is_cached(file_path: str, fingerprint: str) -> bool:
    entry = _cache.get(file_path)
    return entry is not None and entry.get("fp") == fingerprint


def _update_cache(
    file_path: str,
    fp: str,
    file_id: str,
    depth: str,
    chunk_count: int,
) -> None:
    _cache[file_path] = {
        "fp": fp,
        "fid": file_id,
        "depth": depth,
        "chunks": chunk_count,
    }


# ── Scan statistics ──────────────────────────────────────────────────────────

_scan_stats: dict[str, int] = {
    "total": 0,
    "full": 0,
    "ai_preview": 0,
    "card_only": 0,
    "cached": 0,
    "errors": 0,
    "ai_calls": 0,
}


def _reset_stats() -> None:
    for k in _scan_stats:
        _scan_stats[k] = 0


def scan_summary() -> str:
    """Return a human-readable coverage report after bulk ingestion."""
    s = _scan_stats
    total = s["total"]
    if total == 0:
        return "No files scanned."
    ai_pct = 100 * (s["full"] + s["ai_preview"]) / total if total else 0
    lines = [
        "── Coverage Report ──",
        f"  Total files scanned:  {total}",
        f"  Deep (full extract):  {s['full']:>4}  ({100*s['full']/total:.0f}%)",
        f"  AI Preview:           {s['ai_preview']:>4}  ({100*s['ai_preview']/total:.0f}%)",
        f"  Card only:            {s['card_only']:>4}  ({100*s['card_only']/total:.0f}%)",
        f"  Cached (skipped):     {s['cached']:>4}",
        f"  Errors:               {s['errors']:>4}",
        f"  Gemini API calls:     {s['ai_calls']:>4}",
        f"  AI-touched files:     {ai_pct:.0f}%",
    ]
    return "\n".join(lines)


# ── Core: downsampling ──────────────────────────────────────────────────────


def _downsample_chunks(
    chunks: list[Chunk],
    max_chunks: int = MAX_CHUNKS_PER_FILE,
) -> list[Chunk]:
    """Keep first + last + evenly-spaced middle chunks to stay within budget."""
    if len(chunks) <= max_chunks:
        return chunks
    if max_chunks <= 2:
        return chunks[:max_chunks]

    sampled = [chunks[0]]
    inner_budget = max_chunks - 2
    step = (len(chunks) - 2) / (inner_budget + 1)
    for i in range(1, inner_budget + 1):
        idx = int(i * step)
        sampled.append(chunks[idx])
    sampled.append(chunks[-1])

    for new_idx, chunk in enumerate(sampled):
        chunk.chunk_index = new_idx
        chunk.chunk_id = f"{chunk.file_id}:{new_idx}"
    return sampled


# ── Core: low-level ingest ──────────────────────────────────────────────────


def ingest(
    result: ContentResult,
    file_id: str,
    *,
    chunk_size: int = CHUNK_SIZE,
    overlap: int = CHUNK_OVERLAP,
    depth: str = "deep",
) -> IngestResult:
    """
    Low-level ingest: ContentResult → chunks → embeddings → store.

    Callers with pre-extracted content (e.g. tests with synthetic docs) should
    use this directly.  For real files, use ``ingest_file()`` which handles
    classification, extraction, AI preview, and caching.
    """
    file_path = result.filename or result.file_name or ""
    # Derive ext from the actual file path suffix.  result.mime_type is
    # *sometimes* a suffix (".pdf") and sometimes a real MIME type
    # ("application/pdf") depending on the caller.  The file path is
    # always reliable.
    _raw_ext = Path(file_path).suffix.lower() if file_path else ""
    ext = _raw_ext if _raw_ext else (
        result.mime_type if result.mime_type.startswith(".") else ""
    )

    # 1. Chunk (already capped at MAX_EMBED_CHARS)
    content = (result.content or "")[:MAX_EMBED_CHARS]
    chunks: list[Chunk] = chunk_text(
        content,
        file_id=file_id,
        chunk_size=chunk_size,
        overlap=overlap,
    )

    if not chunks:
        return IngestResult(
            file_id=file_id,
            file_path=file_path,
            chunk_count=0,
            skipped=True,
            depth=depth,
            engine=result.engine_used or "",
        )

    # 2. Downsample
    chunks = _downsample_chunks(chunks)

    # 3. Always prepend a file-index sentinel (chunk_index == -1).
    #    This guarantees list_files() can find every indexed file,
    #    regardless of depth.  For deep files the card contains a
    #    content preview; for card/preview the content IS the card.
    if depth == "deep":
        _preview = content[:300].replace("\n", " ").strip()
        card_text = (
            f"[FILE INDEX] This is \"{file_path}\", a {ext} file "
            f"processed by {result.engine_used} ({len(chunks)} content chunks).\n"
            f"Content preview: {_preview}"
        )
    else:
        # card/preview: the first chunk's text is already the rich card
        card_text = chunks[0].text
    card = Chunk(
        chunk_id=f"{file_id}:card",
        file_id=file_id,
        chunk_index=-1,
        text=card_text,
    )
    all_chunks = [card] + chunks

    # 4. Embed
    errors: list[str] = []
    try:
        embeddings = embed_batch([c.text for c in all_chunks])
    except Exception as exc:
        return IngestResult(
            file_id=file_id,
            file_path=file_path,
            chunk_count=0,
            depth=depth,
            engine=result.engine_used or "",
            errors=[f"Embedding failed: {exc}"],
        )

    # 5. Delete old chunks (idempotency)
    try:
        store.delete_by_file_id(file_id)
    except Exception as exc:
        errors.append(f"Delete warning: {exc}")

    # 6. Upsert
    try:
        store.upsert_chunks(
            chunks=all_chunks,
            embeddings=embeddings,
            file_path=file_path,
            ext=ext,
            depth=depth,
        )
    except Exception as exc:
        errors.append(f"Upsert failed: {exc}")
        return IngestResult(
            file_id=file_id,
            file_path=file_path,
            chunk_count=0,
            depth=depth,
            engine=result.engine_used or "",
            errors=errors,
        )

    return IngestResult(
        file_id=file_id,
        file_path=file_path,
        chunk_count=len(all_chunks),
        depth=depth,
        engine=result.engine_used or "",
        errors=errors,
    )


async def _ingest_async(
    result: ContentResult,
    file_id: str,
    **kwargs,
) -> IngestResult:
    """Async wrapper: runs sync ``ingest()`` in a thread so embed_batch
    doesn't block the event loop.  Gated by ``_EMBED_SEM`` so concurrent
    callers don't saturate the threadpool / embedding endpoint."""
    async with _EMBED_SEM:
        return await asyncio.to_thread(ingest, result, file_id, **kwargs)


# ── Smart file-level ingest (3-Layer) ────────────────────────────────────────


async def ingest_file(
    file_path: Path | str,
    file_id: str | None = None,
    force_deep: bool = False,
) -> IngestResult:
    """
    Smart 3-layer file ingestion: classify → extract → AI preview → embed → store.

    Layer A (always): Rich file card with metadata, folder context, filename tokens.
    Layer B (targeted): Gemini AI preview for images and document summaries.
    Layer C (on-demand): Full extraction via ``force_deep=True``.

    Normal mode uses LOCAL extraction for text/code/PDF/office and BOUNDED
    Gemini calls for AI previews (image captions, document summaries).
    """
    file_path = Path(file_path).resolve()

    if file_id is None:
        file_id = hashlib.sha256(str(file_path).encode()).hexdigest()[:16]

    # ── Fingerprint + cache check ─────────────────────────────────────
    fp = _fingerprint(file_path)
    if not force_deep and fp and _is_cached(str(file_path), fp):
        cached = _cache[str(file_path)]
        _scan_stats["total"] += 1
        _scan_stats["cached"] += 1
        return IngestResult(
            file_id=file_id,
            file_path=str(file_path),
            chunk_count=cached.get("chunks", 0),
            skipped=True,
            depth=cached.get("depth", "deep"),
            engine="cached",
        )

    # ── Directories (.app bundles etc.) ───────────────────────────────
    if file_path.is_dir():
        ext = file_path.suffix.lower() or ".dir"
        card = _make_file_card(file_path, ext)
        cr = ContentResult(
            filename=str(file_path), file_name=str(file_path),
            mime_type=ext, category="directory",
            content=card, text=card, engine_used="card",
        )
        result = await _ingest_async(cr, file_id, depth="card")
        _scan_stats["total"] += 1
        _scan_stats["card_only"] += 1
        if fp:
            _update_cache(str(file_path), fp, file_id, "card", result.chunk_count)
        return result

    # ── Read file bytes once ──────────────────────────────────────────
    try:
        file_bytes = file_path.read_bytes()
    except (OSError, PermissionError) as e:
        _scan_stats["total"] += 1
        _scan_stats["errors"] += 1
        return IngestResult(
            file_id=file_id, file_path=str(file_path),
            chunk_count=0, errors=[str(e)],
        )

    ext = file_path.suffix.lower()

    # ── force_deep: full extraction via dispatcher ────────────────────
    if force_deep:
        return await _ingest_deep(file_path, file_id, file_bytes, ext, fp)

    # ── Classify ──────────────────────────────────────────────────────
    pdf_pages: int | None = None
    if ext == ".pdf":
        pdf_pages = _pdf_page_count(file_bytes)

    strategy = classify_file(ext, len(file_bytes), pdf_pages)

    # ═══════════════════════════════════════════════════════════════════
    #  STRATEGY: FULL — text/code/PDF/office
    # ═══════════════════════════════════════════════════════════════════
    if strategy == "full":
        content, engine = _extract_for_embed(file_path, ext, file_bytes)

        if content.strip():
            # ── Good extraction → full embed + optional AI enrichment ──
            ai_summary = ""
            if ext not in TEXT_LIKE_EXTENSIONS:
                # PDF/office: get AI summary to enrich the card
                async with _AI_SEM:
                    ai_summary = await _ai_summarize_text(content, file_path.name)
                if ai_summary:
                    _scan_stats["ai_calls"] += 1
                    # Prepend summary to content so it gets chunked & embedded
                    content = f"[AI Summary] {ai_summary}\n\n{content}"
                    engine = engine + "+ai"

            cr = ContentResult(
                filename=str(file_path), file_name=str(file_path),
                mime_type=ext, category=_category_for_ext(ext),
                content=content[:MAX_EMBED_CHARS], text=content[:MAX_EMBED_CHARS],
                engine_used=engine,
            )
            result = await _ingest_async(cr, file_id, depth="deep")
            _scan_stats["total"] += 1
            _scan_stats["full"] += 1
            if fp:
                _update_cache(str(file_path), fp, file_id, "deep", result.chunk_count)
            return result

        else:
            # ── Local extraction failed → demote to ai_preview ────────
            # (e.g. scanned PDF with no text, broken office doc)
            strategy = "ai_preview"

    # ═══════════════════════════════════════════════════════════════════
    #  STRATEGY: AI_PREVIEW — images, large PDFs, failed-extraction PDFs
    # ═══════════════════════════════════════════════════════════════════
    if strategy == "ai_preview":
        ai_summary = ""
        engine = "card"

        if ext in IMAGE_EXTENSIONS:
            # Gemini vision caption
            async with _AI_SEM:
                ai_summary = await _ai_caption_image(file_bytes, ext, file_path.name)
            if ai_summary:
                engine = "gemini-vision"
                _scan_stats["ai_calls"] += 1

        elif ext == ".pdf":
            # Try local text first for summary
            local_text, pages = _extract_pdf_local(
                file_bytes, max_chars=AI_PREVIEW_INPUT_CHARS
            )
            if local_text.strip():
                async with _AI_SEM:
                    ai_summary = await _ai_summarize_text(local_text, file_path.name)
                engine = f"local-pdf+ai ({pages}p)" if ai_summary else f"local-pdf ({pages}p)"
            else:
                # Scanned PDF — send to Gemini document understanding
                async with _AI_SEM:
                    ai_summary = await _ai_summarize_pdf_vision(file_bytes, file_path.name)
                engine = "gemini-pdf-vision" if ai_summary else "card"

            if ai_summary:
                _scan_stats["ai_calls"] += 1

        elif ext in OFFICE_EXTENSIONS:
            # Office extraction already failed in the "full" strategy above.
            # .docx/.pptx/.xlsx are ZIP-based binaries — raw UTF-8 decode
            # produces garbage.  Fall through to card-only; the user can
            # trigger deepen_file() (Gemini dispatcher) on demand.
            engine = "office-extraction-failed"

        # Build rich card with AI summary
        depth = "preview" if ai_summary else "card"
        card = _make_file_card(file_path, ext, file_bytes, ai_summary=ai_summary)
        cr = ContentResult(
            filename=str(file_path), file_name=str(file_path),
            mime_type=ext, category=_category_for_ext(ext),
            content=card, text=card, engine_used=engine,
        )
        result = await _ingest_async(cr, file_id, depth=depth)

        _scan_stats["total"] += 1
        _scan_stats["ai_preview" if ai_summary else "card_only"] += 1
        if fp:
            _update_cache(str(file_path), fp, file_id, depth, result.chunk_count)
        return result

    # ═══════════════════════════════════════════════════════════════════
    #  STRATEGY: CARD_ONLY — video/audio/archives/exe/unknown
    # ═══════════════════════════════════════════════════════════════════
    card = _make_file_card(file_path, ext, file_bytes)
    cr = ContentResult(
        filename=str(file_path), file_name=str(file_path),
        mime_type=ext, category=_category_for_ext(ext),
        content=card, text=card, engine_used="card",
    )
    result = await _ingest_async(cr, file_id, depth="card")

    _scan_stats["total"] += 1
    _scan_stats["card_only"] += 1
    if fp:
        _update_cache(str(file_path), fp, file_id, "card", result.chunk_count)
    return result


async def _ingest_deep(
    file_path: Path,
    file_id: str,
    file_bytes: bytes,
    ext: str,
    fp: str,
) -> IngestResult:
    """Force-deep path: use Gemini dispatcher for full extraction."""
    # Try Gemini-backed dispatcher (AI call — gated by _AI_SEM)
    try:
        from services.file_processor.dispatcher import extract as dispatch_extract
        async with _AI_SEM:
            cr = await dispatch_extract(file_bytes, file_path.name)
        content = (cr.content or "")[:MAX_EMBED_CHARS]
        engine = cr.engine_used or "gemini"
    except Exception:
        # Fall back to local extraction
        content, engine = _extract_for_embed(file_path, ext, file_bytes)

    if not content.strip():
        # Nothing extracted even with dispatcher — store card
        card = _make_file_card(file_path, ext, file_bytes)
        cr = ContentResult(
            filename=str(file_path), file_name=str(file_path),
            mime_type=ext, category=_category_for_ext(ext),
            content=card, text=card, engine_used="card",
        )
        return await _ingest_async(cr, file_id, depth="card")

    cr = ContentResult(
        filename=str(file_path), file_name=str(file_path),
        mime_type=ext, category=_category_for_ext(ext),
        content=content, text=content, engine_used=engine,
    )
    result = await _ingest_async(cr, file_id, depth="deep")

    # Update cache
    if fp:
        _update_cache(str(file_path), fp, file_id, "deep", result.chunk_count)

    return result


async def deepen_file(
    file_path: Path | str,
    file_id: str | None = None,
) -> IngestResult:
    """Force full extraction + re-embedding via Gemini dispatcher.

    Replaces existing card/preview record with full content chunks.
    Called automatically by ``ask()`` when top hits need more detail.
    """
    return await ingest_file(file_path, file_id=file_id, force_deep=True)


# ── Search ───────────────────────────────────────────────────────────────────


def search(
    query: str,
    k: int = 5,
    where: dict | None = None,
    max_per_file: int = 3,
) -> list[SearchHit]:
    """
    Semantic search with diversity filtering.

    Retrieves extra candidates then caps results per file_id so no single
    file dominates.
    """
    fetch_k = max(k * 4, 20)
    query_embedding = embed_text(query)
    raw_hits = store.query(query_embedding, k=fetch_k, where=where)

    file_counts: dict[str, int] = {}
    diverse: list[SearchHit] = []
    for hit in raw_hits:
        count = file_counts.get(hit.file_id, 0)
        if count < max_per_file:
            diverse.append(hit)
            file_counts[hit.file_id] = count + 1
            if len(diverse) >= k:
                break

    return diverse


async def _search_async(
    query: str,
    k: int = 5,
    where: dict | None = None,
    max_per_file: int = 3,
) -> list[SearchHit]:
    """Async search gated by ``_EMBED_SEM``.

    ``search()`` calls ``embed_text(query)`` synchronously.  This wrapper
    ensures concurrent ``ask()`` calls don't hammer the embedding endpoint
    in parallel.
    """
    async with _EMBED_SEM:
        return await asyncio.to_thread(search, query, k, where, max_per_file)


# ── RAG ──────────────────────────────────────────────────────────────────────

_RAG_SYSTEM = """\
You are Wisp — a smart, friendly file-system memory.  You know the user's
files inside and out because their contents have been indexed.

When answering:
- Be concise and natural — talk like a helpful friend, not a corporate bot.
  No filler phrases like "Based on the information provided" or "I'd be happy to help".
- Synthesise across files when relevant.  Don't just parrot chunks back.
- Cite files naturally: "your resume mentions…", "that Q3 report shows…",
  "the screenshot from dashboard.png has…"
- For broad questions ("what's in here?"), give a quick birds-eye overview
  of what kinds of files exist and what they cover.
- If something's only indexed by metadata (name/type/size but no contents),
  mention it exists but note you can't see inside it yet — they could
  request a deeper analysis.
- If the excerpts don't answer the question, say so plainly — but mention
  what IS available so they know what to ask about.
- Keep it tight.  No essays unless they ask for detail.
"""


def _build_rag_prompt(query: str, hits: list[SearchHit]) -> str:
    """Build the user-role prompt that includes retrieved context."""
    parts: list[str] = ["### Retrieved excerpts\n"]
    for i, h in enumerate(hits, 1):
        label = h.file_path or h.file_id
        if h.depth == "card":
            tag = " [card only — no content extracted yet]"
        elif h.depth == "preview":
            tag = " [AI preview]"
        else:
            tag = ""
        parts.append(f"[{i}] Source: {label}{tag}\n{h.text}\n")
    parts.append(f"### Question\n{query}")
    return "\n".join(parts)


async def ask(
    query: str,
    k: int = 15,
    where: dict | None = None,
    auto_deepen: bool = True,
) -> AskResult:
    """
    RAG pipeline: retrieve → optionally deepen card/preview hits → answer.

    When ``auto_deepen`` is True, top-5 hits that aren't fully extracted
    get deepened via Gemini before generating the answer.
    """
    hits = await _search_async(query, k, where)
    if not hits:
        return AskResult(
            answer="I couldn't find any relevant information in the indexed files.",
            hits=[], query=query,
        )

    # Auto-deepen non-deep files among top results (allowlisted types only)
    deepened: list[str] = []
    if auto_deepen:
        shallow_hits = [
            h for h in hits[:5]
            if h.depth != "deep"
            and h.file_path
            and Path(h.file_path).suffix.lower() in DEEPEN_EXTENSIONS
        ]
        for hit in shallow_hits[:3]:
            fpath = Path(hit.file_path)
            if fpath.exists():
                # deepen_file → ingest_file → _ingest_async already
                # acquires _EMBED_SEM internally; _AI_SEM is acquired
                # inside _ingest_deep around dispatch_extract.
                result = await deepen_file(fpath, hit.file_id)
                if result.depth == "deep" and result.chunk_count > 0:
                    deepened.append(hit.file_path)
        if deepened:
            hits = await _search_async(query, k, where)

    prompt = _build_rag_prompt(query, hits)
    async with _AI_SEM:
        answer = await generate_text(prompt, system=_RAG_SYSTEM)
    return AskResult(answer=answer, hits=hits, query=query, deepened_files=deepened)


# ── Deletion ─────────────────────────────────────────────────────────────────


def delete_file(file_id: str) -> None:
    """Remove all chunks for a file from the vector store."""
    store.delete_by_file_id(file_id)
    # Also remove from cache
    for key, val in list(_cache.items()):
        if val.get("fid") == file_id:
            del _cache[key]


# ── Store lifecycle ──────────────────────────────────────────────────────────


def init_store(db_path: str | None = None) -> None:
    """Initialise the vector store + fingerprint cache + reset scan stats."""
    store.init(db_path=db_path)
    _init_cache(db_path)
    _reset_stats()


def teardown_store() -> None:
    """Close the vector store and save the fingerprint cache."""
    _save_cache()
    store.teardown()
    global _cache, _cache_path
    _cache = {}
    _cache_path = None

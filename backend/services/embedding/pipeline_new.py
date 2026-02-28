"""
Embedding pipeline — preview-first smart ingestion.

Architecture
------------
  1. PREVIEW everything: every file gets metadata + preview text, stored and
     embedded so it's searchable.  No Gemini API calls for previews.
  2. EMBED selectively: text/code/PDF/office get full chunking + embedding
     with hard caps.  Media/archives/executables stay preview-only.
  3. DEEPEN on demand: when a query hits preview-only files, auto-extract
     and embed them (uses Gemini) for better retrieval.
  4. CACHE by fingerprint (path+size+mtime) so re-runs skip unchanged files.

Public API
----------
  ingest(result, file_id)          — Low-level: ContentResult → store
  ingest_file(file_path, file_id)  — Smart: classify → extract → store
  deepen_file(file_path, file_id)  — Force full extraction for a preview file
  search(query, k)                 — Semantic search with diversity
  ask(query, k)                    — RAG with auto-deepening
  delete_file(file_id)             — Remove a file's chunks from store
  init_store(db_path)              — Initialise vector store + cache
  teardown_store()                 — Close store + save cache
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import json
from dataclasses import dataclass, field
from pathlib import Path

from ai.embed import embed_batch, embed_text
from ai.generate import generate_text
from services.embedding.chunker import Chunk, chunk_text
from services.embedding import store
from services.embedding.store import SearchHit
from services.file_processor.models import ContentResult


# ── Optional local PDF extraction ─────────────────────────────────────────────

try:
    from pypdf import PdfReader as _PdfReader
    _HAS_PYPDF = True
except ImportError:
    _HAS_PYPDF = False


# ── Ingest policy constants ──────────────────────────────────────────────────

MAX_EMBED_CHARS     = 30_000    # Hard cap on chars to embed per file
MAX_CHUNKS_PER_FILE = 12        # Hard cap on chunks after chunking
PREVIEW_CHARS       = 500       # Content preview for preview-only records
MAX_PDF_PAGES_EMBED = 80        # PDFs above this → preview-only
CHUNK_SIZE          = 800       # Characters per chunk
CHUNK_OVERLAP       = 100       # Overlap between chunks

# ── Extension sets ────────────────────────────────────────────────────────────

MEDIA_EXTENSIONS = frozenset({
    # Images
    ".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif", ".gif", ".svg",
    ".ico", ".icns",
    # Video
    ".mp4", ".mov", ".avi", ".webm", ".mkv", ".flv", ".wmv", ".3gp",
    ".mpeg", ".mpg",
    # Audio
    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".aiff",
})

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


# ── Result types ─────────────────────────────────────────────────────────────


@dataclass
class IngestResult:
    file_id: str
    file_path: str
    chunk_count: int
    skipped: bool = False          # True when cached / nothing to embed
    is_preview: bool = False       # True when only metadata was indexed
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
    """Return ``'embed'`` or ``'preview'`` based on file type.

    - Media (images/audio/video)  → ``'preview'``  (no Gemini in bulk)
    - Text / code / markup        → ``'embed'``    (local decode, always)
    - PDFs ≤ 80 pages             → ``'embed'``    (local pypdf extraction)
    - PDFs > 80 pages             → ``'preview'``  (too large for bulk)
    - Office                      → ``'embed'``    (local extractor)
    - Archives / executables      → ``'preview'``
    """
    if ext in MEDIA_EXTENSIONS:
        return "preview"
    if ext in TEXT_LIKE_EXTENSIONS:
        return "embed"
    if ext == ".pdf":
        if pdf_pages is not None and pdf_pages > MAX_PDF_PAGES_EMBED:
            return "preview"
        return "embed"
    if ext in OFFICE_EXTENSIONS:
        return "embed"
    if ext in ARCHIVE_EXTENSIONS:
        return "preview"
    if ext in EXECUTABLE_EXTENSIONS:
        return "preview"
    # Unknown → preview
    return "preview"


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


def _make_preview(
    file_path: Path,
    ext: str,
    file_bytes: bytes | None = None,
) -> str:
    """Build a preview record for any file: metadata + optional content peek."""
    name = file_path.name
    try:
        size = file_path.stat().st_size
    except OSError:
        size = len(file_bytes) if file_bytes else 0
    size_str = _human_size(size)
    type_desc = _TYPE_MAP.get(ext, f"file ({ext})")

    peek = ""
    if file_bytes:
        if ext in TEXT_LIKE_EXTENSIONS:
            try:
                peek = file_bytes[:PREVIEW_CHARS * 2].decode("utf-8", errors="replace").strip()
                peek = peek[:PREVIEW_CHARS]
            except Exception:
                pass
        elif ext == ".pdf":
            text, _ = _extract_pdf_local(file_bytes, max_chars=PREVIEW_CHARS)
            peek = text.strip()[:PREVIEW_CHARS]

    lines = [
        f"File: {name}",
        f"Type: {type_desc}",
        f"Size: {size_str}",
    ]
    if peek:
        lines.append(f"Content preview: {peek}")
    else:
        lines.append(
            f"This {type_desc} named \"{name}\" ({size_str}) is in the user's files. "
            "Full contents not yet extracted — ask to deep-analyze this file for details."
        )
    return "\n".join(lines)


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
    is_preview: bool,
    chunk_count: int,
) -> None:
    _cache[file_path] = {
        "fp": fp,
        "fid": file_id,
        "preview": is_preview,
        "chunks": chunk_count,
    }


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
    is_preview: bool = False,
) -> IngestResult:
    """
    Low-level ingest: ContentResult → chunks → embeddings → store.

    Callers with pre-extracted content (e.g. tests with synthetic docs) should
    use this directly.  For real files, use ``ingest_file()`` which handles
    classification, extraction, capping, and caching automatically.
    """
    file_path = result.filename or result.file_name or ""
    ext = result.mime_type

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
            is_preview=is_preview,
            engine=result.engine_used or "",
        )

    # 2. Downsample
    chunks = _downsample_chunks(chunks)

    # 3. Prepend file index card (content preview for semantic matching)
    _preview = content[:300].replace("\n", " ").strip()
    card_text = (
        f"[FILE INDEX] This is \"{file_path}\", a {ext} file "
        f"processed by {result.engine_used} ({len(chunks)} content chunks).\n"
        f"Content preview: {_preview}"
    )
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
            is_preview=is_preview,
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
            is_preview=is_preview,
        )
    except Exception as exc:
        errors.append(f"Upsert failed: {exc}")
        return IngestResult(
            file_id=file_id,
            file_path=file_path,
            chunk_count=0,
            is_preview=is_preview,
            engine=result.engine_used or "",
            errors=errors,
        )

    return IngestResult(
        file_id=file_id,
        file_path=file_path,
        chunk_count=len(all_chunks),
        is_preview=is_preview,
        engine=result.engine_used or "",
        errors=errors,
    )


# ── Smart file-level ingest ─────────────────────────────────────────────────


def ingest_file(
    file_path: Path | str,
    file_id: str | None = None,
    force_deep: bool = False,
) -> IngestResult:
    """
    Smart single-file ingestion: classify → extract locally → embed → store.

    In normal mode (``force_deep=False``), all extraction is LOCAL:
      - Text/code → UTF-8 decode
      - PDFs → pypdf text extraction
      - Office → python-docx / openpyxl etc.
      - Media / archives / executables → preview-only (metadata)

    **No Gemini API calls** in normal mode.  This is what makes bulk fast.

    With ``force_deep=True`` (used by ``deepen_file()``), media and scanned
    PDFs are sent through the Gemini-backed dispatcher for full extraction.
    """
    file_path = Path(file_path)

    if file_id is None:
        file_id = hashlib.sha256(str(file_path).encode()).hexdigest()[:16]

    # Fingerprint + cache check
    fp = _fingerprint(file_path)
    if not force_deep and fp and _is_cached(str(file_path), fp):
        cached = _cache[str(file_path)]
        return IngestResult(
            file_id=file_id,
            file_path=str(file_path),
            chunk_count=cached.get("chunks", 0),
            skipped=True,
            is_preview=cached.get("preview", False),
            engine="cached",
        )

    # Handle directories (e.g. .app bundles)
    if file_path.is_dir():
        ext = file_path.suffix.lower() or ".dir"
        content = _make_preview(file_path, ext)
        cr = ContentResult(
            filename=file_path.name, file_name=file_path.name,
            mime_type=ext, category="directory",
            content=content, text=content, engine_used="preview",
        )
        result = ingest(cr, file_id, is_preview=True)
        if fp:
            _update_cache(str(file_path), fp, file_id, True, result.chunk_count)
        return result

    # Read file bytes once
    try:
        file_bytes = file_path.read_bytes()
    except (OSError, PermissionError) as e:
        return IngestResult(
            file_id=file_id, file_path=str(file_path),
            chunk_count=0, errors=[str(e)],
        )

    ext = file_path.suffix.lower()

    # Classify
    pdf_pages: int | None = None
    if ext == ".pdf":
        pdf_pages = _pdf_page_count(file_bytes)

    strategy = "embed" if force_deep else classify_file(ext, len(file_bytes), pdf_pages)

    # Extract
    if strategy == "preview":
        content = _make_preview(file_path, ext, file_bytes)
        engine = "preview"
        is_preview = True

    elif force_deep and ext in MEDIA_EXTENSIONS:
        # Deepening media → use Gemini via dispatcher
        try:
            from services.file_processor.dispatcher import extract as dispatch_extract
            cr = asyncio.run(dispatch_extract(file_bytes, file_path.name))
            content = (cr.content or "")[:MAX_EMBED_CHARS]
            engine = cr.engine_used or "gemini"
            is_preview = False
        except Exception:
            content = _make_preview(file_path, ext, file_bytes)
            engine = "preview"
            is_preview = True

    elif force_deep and ext == ".pdf":
        # Deepening PDF → try Gemini, fall back to local
        try:
            from services.file_processor.dispatcher import extract as dispatch_extract
            cr = asyncio.run(dispatch_extract(file_bytes, file_path.name))
            content = (cr.content or "")[:MAX_EMBED_CHARS]
            engine = cr.engine_used or "gemini"
            is_preview = False
        except Exception:
            content, _ = _extract_pdf_local(file_bytes)
            engine = "local-pdf"
            is_preview = not bool(content.strip())

    else:
        # Normal embed path — all local
        content, engine = _extract_for_embed(file_path, ext, file_bytes)
        is_preview = not bool(content.strip())

    # Fallback: if extraction yielded nothing, make a preview
    if not content.strip():
        content = _make_preview(file_path, ext, file_bytes)
        engine = "preview"
        is_preview = True

    # Build ContentResult and ingest
    cr = ContentResult(
        filename=file_path.name,
        file_name=file_path.name,
        mime_type=ext,
        category=_category_for_ext(ext),
        content=content,
        text=content,
        engine_used=engine,
    )
    result = ingest(cr, file_id, is_preview=is_preview)
    result.is_preview = is_preview
    result.engine = engine

    # Update cache
    if fp:
        _update_cache(str(file_path), fp, file_id, is_preview, result.chunk_count)

    return result


def deepen_file(
    file_path: Path | str,
    file_id: str | None = None,
) -> IngestResult:
    """Force full extraction + re-embedding of a previously preview-only file.

    Uses the Gemini-backed dispatcher for media and scanned PDFs.
    Replaces the old preview record with full content chunks.
    """
    return ingest_file(file_path, file_id=file_id, force_deep=True)


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
        tag = " [preview-only]" if h.is_preview else ""
        parts.append(f"[{i}] Source: {label}{tag}\n{h.text}\n")
    parts.append(f"### Question\n{query}")
    return "\n".join(parts)


def ask(
    query: str,
    k: int = 15,
    where: dict | None = None,
    auto_deepen: bool = True,
) -> AskResult:
    """
    RAG pipeline: retrieve → optionally deepen preview-only hits → answer.

    When ``auto_deepen`` is True, any preview-only files in the top-5 hits
    are fully extracted (via Gemini) before generating the answer.  This
    gives the "improving results…" experience.
    """
    hits = search(query, k=k, where=where)
    if not hits:
        return AskResult(
            answer="I couldn't find any relevant information in the indexed files.",
            hits=[], query=query,
        )

    # Auto-deepen preview-only files among top results
    deepened: list[str] = []
    if auto_deepen:
        preview_hits = [h for h in hits[:5] if h.is_preview and h.file_path]
        for hit in preview_hits[:3]:
            fp = Path(hit.file_path)
            if fp.exists():
                result = deepen_file(fp, hit.file_id)
                if not result.is_preview and result.chunk_count > 0:
                    deepened.append(hit.file_path)
        if deepened:
            hits = search(query, k=k, where=where)

    prompt = _build_rag_prompt(query, hits)
    answer = asyncio.run(generate_text(prompt, system=_RAG_SYSTEM))
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
    """Initialise the vector store + fingerprint cache."""
    store.init(db_path=db_path)
    _init_cache(db_path)


def teardown_store() -> None:
    """Close the vector store and save the fingerprint cache."""
    _save_cache()
    store.teardown()
    global _cache, _cache_path
    _cache = {}
    _cache_path = None

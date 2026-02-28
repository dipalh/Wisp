"""
Wisp — Embedding Pipeline Test Suite
=====================================

Run from the ``backend/`` directory:

  Automated (14 tests, exit 0 / 1):
    python -m tests.test_embed_pipeline

  Interactive — point Wisp at a real directory and ask questions:
    python -m tests.test_embed_pipeline -i --dir ~/Documents/MyProject

  Interactive — specific files (any type: images, PDFs, code, etc.):
    python -m tests.test_embed_pipeline -i --files report.pdf photo.png code.py

  Interactive — built-in demo docs (no args):
    python -m tests.test_embed_pipeline -i

All file types supported by the file processor are handled: images, video,
audio, PDFs, Office docs, code, archives, and plain text.  Files are
extracted via the dispatcher (Gemini vision for images/video/audio,
local parsers for Office/text), chunked, embedded, and stored in a temp
LanceDB index.  Then you ask natural-language questions and get AI answers
grounded in the actual file contents.

Structure
---------
  PART 1 — Chunker unit tests          (offline, no API key needed)
  PART 2 — Full pipeline round-trip    (needs GEMINI_API_KEY in .env)

Both modes use an isolated temp LanceDB directory that is deleted on exit.
They never touch your real index.

Every test prints:
    INPUT     — what was given
    EXPECTED  — what we expect to see
    ACTUAL    — what the system returned
    [PASS] / [FAIL]
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import textwrap

# ── allow  python -m tests.test_embed_pipeline  from backend/ ─────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Load .env so GEMINI_API_KEY is available
from pathlib import Path as _Path

_env_path = _Path(__file__).parent.parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(dotenv_path=_env_path, override=False)


# ═══════════════════════════════════════════════════════════════════════════════
# Test helpers
# ═══════════════════════════════════════════════════════════════════════════════

_pass_count = 0
_fail_count = 0


def check(name: str, condition: bool, detail: str = "") -> bool:
    """Print a single test verdict and track pass/fail counts."""
    global _pass_count, _fail_count
    status = "[PASS]" if condition else "[FAIL]"
    print(f"  {status}  {name}")
    if detail:
        for line in detail.splitlines():
            print(f"         {line}")
    if condition:
        _pass_count += 1
    else:
        _fail_count += 1
    return condition


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1 — Chunker  (no network, no vector store)
# ═══════════════════════════════════════════════════════════════════════════════

from services.embedding.chunker import chunk_text


def run_chunker_tests() -> None:
    print("\n" + "=" * 64)
    print("PART 1 — Chunker unit tests  (offline)")
    print("=" * 64)

    # T1: empty → nothing
    chunks = chunk_text("", file_id="f1")
    check("T1: empty text → 0 chunks", len(chunks) == 0, f"got {len(chunks)}")

    # T2: short text → exactly 1 chunk, text preserved
    short = "This is a short document about invoices."
    chunks = chunk_text(short, file_id="f2")
    t2_text = repr(chunks[0].text) if chunks else "—"
    check(
        "T2: short text → 1 chunk with matching text",
        len(chunks) == 1 and chunks[0].text == short,
        f"got {len(chunks)} chunk(s), text={t2_text}",
    )

    # T3: chunk_id format
    t3_id = repr(chunks[0].chunk_id) if chunks else "—"
    check(
        "T3: chunk_id == '<file_id>:<index>'",
        len(chunks) == 1 and chunks[0].chunk_id == "f2:0",
        f"got chunk_id={t3_id}",
    )

    # T4: long text → multiple chunks, no data lost
    long_text = ("word " * 200).strip()  # ~1 000 chars
    chunks = chunk_text(long_text, file_id="f3", chunk_size=200, overlap=20)
    joined = " ".join(c.text for c in chunks)
    all_present = all(w in joined for w in long_text.split())
    check("T4: long text → multiple chunks", len(chunks) > 1, f"got {len(chunks)} chunks")
    check("T4b: no words lost across chunks", all_present)

    # T5: paragraph-aware splitting
    para = "First paragraph.\n\nSecond paragraph."
    chunks = chunk_text(para, file_id="f4", chunk_size=800)
    check("T5: two paragraphs → 2 chunks", len(chunks) == 2, f"got {len(chunks)}")

    # T6: chunk indices are sequential 0-based
    chunks = chunk_text("A.\n\nB.\n\nC.", file_id="f5", chunk_size=800)
    indices = [c.chunk_index for c in chunks]
    check("T6: indices are 0-based sequential", indices == list(range(len(chunks))), f"got {indices}")


# ═══════════════════════════════════════════════════════════════════════════════
# Test documents (used by Part 2 and interactive mode)
# ═══════════════════════════════════════════════════════════════════════════════

DOCS = {
    "file_invoice": {
        "filename": "invoice.txt",
        "text": textwrap.dedent("""\
            INVOICE #2024-0042

            Vendor: Acme Software Ltd.
            Date: 2024-11-15
            Due: 2024-12-15

            Line items:
              - Enterprise license (12 months)  $4,800.00
              - Professional services (40 hrs)  $6,000.00
              - Support package (Basic)           $900.00

            Subtotal:   $11,700.00
            Tax (8 %):     $936.00
            Total due:  $12,636.00

            Payment method: Wire transfer
            Bank: First National Bank
            Account: 987-654-3210
        """),
    },
    "file_resume": {
        "filename": "resume.txt",
        "text": textwrap.dedent("""\
            Jane Smith
            Senior Software Engineer

            EXPERIENCE

            Acme Corp — Lead Backend Engineer (2021–present)
            - Designed distributed payment processing system, handling $2M/day.
            - Migrated monolith to microservices; reduced p99 latency by 40%.
            - Mentored team of 6 engineers.

            Startup XYZ — Python Developer (2018–2021)
            - Built REST APIs with FastAPI and PostgreSQL.
            - Automated CI/CD pipelines with GitHub Actions.

            SKILLS
            Python, Go, TypeScript, PostgreSQL, Redis, Kubernetes, Docker

            EDUCATION
            B.Sc. Computer Science, State University, 2018
        """),
    },
    "file_meeting": {
        "filename": "meeting_notes.txt",
        "text": textwrap.dedent("""\
            Q3 2024 — Engineering All-Hands Notes

            Attendees: Alice, Bob, Carol, David
            Date: 2024-09-10

            Agenda item 1: Roadmap review
            The team reviewed Q3 milestones. The new search feature is 80% complete.
            Alice noted the vector database migration would be finished by end of September.

            Agenda item 2: On-call rotation
            Bob volunteered to take the first October on-call shift.
            Carol raised concerns about alert fatigue — David will audit the alert rules.

            Action items:
            - Alice: finish vector DB migration by 2024-09-30
            - David: audit PagerDuty alert rules
            - Bob: confirm October on-call by 2024-09-12
        """),
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# Setup / teardown helpers  (used by both modes)
# ═══════════════════════════════════════════════════════════════════════════════


def _require_api_key() -> bool:
    """Return True if GEMINI_API_KEY is set, else print skip message."""
    if os.environ.get("GEMINI_API_KEY"):
        return True
    print("\n  [SKIP]  GEMINI_API_KEY not set — skipping pipeline tests.")
    print("          Set it in backend/.env or export it.\n")
    return False


def _create_temp_store() -> str:
    """Create a temp LanceDB dir and init the store there.
    Returns the temp dir path (caller must shutil.rmtree it).
    """
    from services.embedding import pipeline
    tmp = tempfile.mkdtemp(prefix="wisp_test_lancedb_")
    pipeline.init_store(db_path=tmp)
    print(f"  (temp LanceDB dir: {tmp})")
    return tmp


def _ingest_test_docs() -> dict[str, int]:
    """Ingest the three test docs.  Returns {file_id: chunk_count}."""
    from services.embedding import pipeline
    from services.file_processor.models import ContentResult

    counts: dict[str, int] = {}
    for file_id, doc in DOCS.items():
        cr = ContentResult(
            filename=doc["filename"],
            file_name=doc["filename"],
            mime_type="text/plain",
            category="text",
            content=doc["text"],
            text=doc["text"],
        )
        result = pipeline.ingest(cr, file_id=file_id)
        counts[file_id] = result.chunk_count
        if result.errors:
            print(f"    WARNING: {file_id} → errors: {result.errors}")
    return counts


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2 — Full pipeline round-trip
# ═══════════════════════════════════════════════════════════════════════════════


def run_pipeline_tests() -> None:
    print("\n" + "=" * 64)
    print("PART 2 — Pipeline round-trip  (Gemini API + LanceDB)")
    print("=" * 64)

    if not _require_api_key():
        return

    from services.embedding import pipeline, store

    tmp = _create_temp_store()
    try:
        _run_pipeline_checks(pipeline, store)
    finally:
        pipeline.teardown_store()
        shutil.rmtree(tmp, ignore_errors=True)


def _run_pipeline_checks(pipeline, store) -> None:
    # ── T7 + T8: ingest all 3 docs ───────────────────────────────────────────
    print("\n  ── T7/T8: Ingest all documents ──")
    counts = _ingest_test_docs()
    invoice_count = counts.get("file_invoice", 0)
    total = store.collection_count()
    print(f"    INPUT    : 3 documents ({sum(len(d['text']) for d in DOCS.values())} chars total)")
    print(f"    EXPECTED : each file produces >0 chunks")
    print(f"    ACTUAL   : invoice={invoice_count}, resume={counts.get('file_resume',0)}, "
          f"meeting={counts.get('file_meeting',0)}, total={total}")
    check("T7: invoice chunk_count > 0", invoice_count > 0)
    check("T8: all three → total > 0", total > 0, f"total={total}")

    # ── T9: semantic query → invoice ──────────────────────────────────────────
    print("\n  ── T9: Query 'invoice total amount due' ──")
    hits = pipeline.search("invoice total amount due", k=3)
    _print_hits("invoice total amount due", "file_invoice", hits)
    check("T9: top hit is file_invoice", hits and hits[0].file_id == "file_invoice")

    # ── T10: semantic query → resume ──────────────────────────────────────────
    print("\n  ── T10: Query 'Python backend engineer experience' ──")
    hits = pipeline.search("Python backend engineer experience", k=3)
    _print_hits("Python backend engineer experience", "file_resume", hits)
    check("T10: top hit is file_resume", hits and hits[0].file_id == "file_resume")

    # ── T11: idempotency ──────────────────────────────────────────────────────
    print("\n  ── T11: Re-ingest invoice (idempotency) ──")
    before = store.collection_count()
    from services.file_processor.models import ContentResult
    cr = ContentResult(
        filename="invoice.txt", file_name="invoice.txt",
        mime_type="text/plain", category="text",
        content=DOCS["file_invoice"]["text"], text=DOCS["file_invoice"]["text"],
    )
    pipeline.ingest(cr, file_id="file_invoice")
    after = store.collection_count()
    print(f"    INPUT    : re-ingest same invoice.txt")
    print(f"    EXPECTED : chunk count unchanged (no duplicates)")
    print(f"    ACTUAL   : before={before}, after={after}")
    check("T11: re-ingest → count unchanged", before == after)

    # ── T12: delete ───────────────────────────────────────────────────────────
    print("\n  ── T12: Delete invoice ──")
    before = store.collection_count()
    pipeline.delete_file("file_invoice")
    after = store.collection_count()
    removed = before - after
    print(f"    INPUT    : delete_file('file_invoice')")
    print(f"    EXPECTED : count decreases by {invoice_count}")
    print(f"    ACTUAL   : before={before}, after={after}, removed={removed}")
    check("T12: delete removes correct chunks", removed == invoice_count)

    # ── T13: query after delete ───────────────────────────────────────────────
    print("\n  ── T13: Query after delete ──")
    hits = pipeline.search("invoice total amount due", k=3)
    found = any(h.file_id == "file_invoice" for h in hits)
    print(f"    EXPECTED : file_invoice NOT in results")
    print(f"    ACTUAL   :")
    for i, h in enumerate(hits):
        print(f"      [{i+1}] file_id={h.file_id}  score={h.score:.4f}")
    check("T13: deleted file absent from results", not found)


def _print_hits(query: str, expected_top: str, hits) -> None:
    print(f"    INPUT    : query = {query!r}")
    print(f"    EXPECTED : top hit from {expected_top}")
    print(f"    ACTUAL   :")
    for i, h in enumerate(hits):
        print(f"      [{i+1}] file_id={h.file_id}  score={h.score:.4f}")
        # Show up to 100 chars of the chunk text so you can read it
        snippet = h.text[:100].replace("\n", " ")
        print(f"           \"{snippet}...\"")


# ═══════════════════════════════════════════════════════════════════════════════
# Interactive mode
# ═══════════════════════════════════════════════════════════════════════════════

# ── File size thresholds ──────────────────────────────────────────────────────
MAX_GEMINI_FILE_SIZE_MB = 20     # Gemini API upload limit for media

# ── Directories to always skip (structural noise, not user files) ─────────────
_SKIP_DIR_NAMES = {
    "__pycache__", "node_modules", ".git", ".venv", "venv", ".tox",
    "dist", "build", ".eggs", ".mypy_cache", ".idea", ".vscode",
}


def _should_skip_dir(name: str) -> bool:
    """Return True for directories that are filesystem noise, not user content."""
    lower = name.lower()
    if lower.startswith(".") and lower not in {".app"}:
        return True
    if lower in _SKIP_DIR_NAMES:
        return True
    # Saved-webpage companion dirs (e.g. "Checkout _ eBay_files") — assets, not content
    if lower.endswith("_files"):
        return True
    # macOS localization dirs — hundreds of .strings files, no user content
    if lower.endswith(".lproj"):
        return True
    return False


def _file_metadata_description(path: _Path) -> str:
    """Build a rich metadata string for a file we can't fully extract.

    This ensures the system *knows* about every file — name, type, size,
    location — even if it can't read the contents.
    """
    name = path.name
    ext = path.suffix.lower() or "(no extension)"
    try:
        stat = path.stat()
        size = stat.st_size
        if size < 1024:
            size_str = f"{size} bytes"
        elif size < 1024 * 1024:
            size_str = f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            size_str = f"{size / (1024 * 1024):.1f} MB"
        else:
            size_str = f"{size / (1024 * 1024 * 1024):.2f} GB"
    except OSError:
        size_str = "unknown size"

    # Human-readable type descriptions
    type_map = {
        ".dmg": "macOS disk image (installer)",
        ".iso": "disk image (ISO)",
        ".img": "disk image",
        ".torrent": "BitTorrent download file",
        ".exe": "Windows executable",
        ".msi": "Windows installer package",
        ".dll": "Windows dynamic library",
        ".app": "macOS application bundle",
        ".pkg": "macOS installer package",
        ".deb": "Linux Debian package",
        ".rpm": "Linux RPM package",
        ".woff": "web font (WOFF)",
        ".woff2": "web font (WOFF2)",
        ".ttf": "TrueType font",
        ".eot": "Embedded OpenType font",
        ".otf": "OpenType font",
        ".ico": "icon file",
        ".icns": "macOS icon file",
        ".save": "game save file",
        ".pkpass": "Apple Wallet pass",
        ".pbids": "Power BI data source",
        ".plist": "macOS property list (config)",
        ".strings": "macOS localization strings",
        ".nib": "macOS Interface Builder file",
        ".storyboardc": "compiled storyboard (iOS/macOS)",
        ".vmdk": "virtual machine disk (VMware)",
        ".vdi": "virtual machine disk (VirtualBox)",
        ".pyc": "compiled Python bytecode",
        ".pyo": "optimized Python bytecode",
        ".class": "compiled Java class",
        ".o": "compiled object file",
        ".obj": "compiled object file",
        ".lock": "dependency lock file",
        ".bin": "binary data file",
        ".dat": "data file",
        ".ds_store": "macOS Finder metadata",
        ".backup": "backup file",
        ".bak": "backup file",
        ".tmp": "temporary file",
        ".crdownload": "incomplete Chrome download",
        ".part": "incomplete download",
        ".zip": "ZIP archive",
        ".tar": "TAR archive",
        ".gz": "gzip compressed file",
        ".tgz": "compressed TAR archive",
        ".rar": "RAR archive",
        ".7z": "7-Zip archive",
        ".bz2": "bzip2 compressed file",
        ".xz": "XZ compressed file",
    }

    type_desc = type_map.get(ext, f"file (type: {ext})")

    return (
        f"File: {name}\n"
        f"Type: {type_desc}\n"
        f"Extension: {ext}\n"
        f"Size: {size_str}\n"
        f"This is a {type_desc} named \"{name}\" ({size_str}). "
        f"The file contents cannot be fully extracted but the file exists "
        f"in the user's file system."
    )


def _collect_files_from_dir(
    dir_path: str,
    max_files: int = 2000,
    recursive: bool = True,
) -> list[_Path]:
    """Collect ALL files from a directory.

    Only skips structural directories (.git, node_modules, _files/, .lproj)
    that are filesystem noise. Every actual file is returned.
    """
    root = _Path(dir_path).resolve()
    if not root.is_dir():
        print(f"  ERROR: {root} is not a directory")
        return []

    files: list[_Path] = []
    skipped_dirs: list[str] = []

    def _walk(directory: _Path, depth: int = 0) -> None:
        if len(files) >= max_files:
            return
        try:
            entries = sorted(directory.iterdir())
        except PermissionError:
            return

        for item in entries:
            if len(files) >= max_files:
                return

            if item.is_dir():
                if _should_skip_dir(item.name):
                    skipped_dirs.append(item.name)
                    continue
                # .app bundles — index the .app itself as a single entry
                if item.name.lower().endswith(".app"):
                    # Create a placeholder path for the app bundle
                    files.append(item)
                    continue
                if recursive:
                    _walk(item, depth + 1)
                continue

            if not item.is_file():
                continue

            # Hidden files — still index, but skip .DS_Store specifically
            if item.name == ".DS_Store":
                continue

            files.append(item)

    _walk(root)

    if skipped_dirs:
        from collections import Counter
        dir_counts = Counter(skipped_dirs)
        print(f"  (Skipped {len(skipped_dirs)} structural directories: "
              + ", ".join(f"{n}" for n, _ in dir_counts.most_common(5))
              + ("..." if len(dir_counts) > 5 else "") + ")")

    return files


def _resolve_file_list(file_paths: list[str]) -> list[_Path]:
    """Resolve explicit --files paths."""
    result: list[_Path] = []
    for path in file_paths:
        p = _Path(path).resolve()
        if not p.is_file():
            print(f"    ⚠ skipping (not a file): {p}")
            continue
        result.append(p)
    return result


def _categorize_ext(ext: str) -> str:
    """Map extension to a display category."""
    if ext in {".pdf"}:
        return "PDFs"
    if ext in {".png", ".jpg", ".jpeg", ".webp", ".heic", ".heif", ".gif", ".svg", ".ico", ".icns"}:
        return "Images"
    if ext in {".mp4", ".mov", ".avi", ".webm", ".mkv", ".flv", ".wmv", ".3gp", ".mpeg", ".mpg"}:
        return "Videos"
    if ext in {".mp3", ".wav", ".m4a", ".aac", ".ogg", ".flac", ".opus", ".aiff"}:
        return "Audio"
    if ext in {".docx", ".pptx", ".xlsx", ".doc", ".ppt", ".xls"}:
        return "Office"
    if ext in {".html", ".htm"}:
        return "HTML"
    if ext in {".csv", ".json", ".xml", ".yaml", ".yml", ".toml"}:
        return "Data"
    if ext in {".zip", ".tar", ".gz", ".tgz", ".rar", ".7z", ".bz2", ".xz"}:
        return "Archives"
    if ext in {".dmg", ".iso", ".img", ".pkg", ".deb", ".rpm", ".msi", ".exe", ".dll", ".app"}:
        return "Installers/Apps"
    if ext in {".torrent", ".save", ".pkpass", ".pbids", ".plist", ".strings", ".nib", ".storyboardc"}:
        return "System/Meta"
    if ext in {".woff", ".woff2", ".ttf", ".eot", ".otf"}:
        return "Fonts"
    if ext in {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".go", ".rs", ".rb",
               ".php", ".swift", ".kt", ".sh", ".bash", ".h", ".hpp", ".m", ".r", ".lua", ".pl",
               ".zig", ".sol", ".tex", ".sql"}:
        return "Code"
    if ext in {".txt", ".md", ".log", ".cfg", ".conf", ".ini"}:
        return "Text"
    return "Other"


def _print_scan_summary(files: list[_Path], root: _Path) -> None:
    """Show what we found — every file counts."""
    from collections import Counter

    cats: Counter[str] = Counter()
    for f in files:
        ext = f.suffix.lower() if f.is_file() else ".app"
        cats[_categorize_ext(ext)] += 1

    total_size = 0
    for f in files:
        try:
            total_size += f.stat().st_size if f.is_file() else 0
        except OSError:
            pass

    if total_size < 1024 * 1024:
        size_str = f"{total_size / 1024:.0f} KB"
    elif total_size < 1024 * 1024 * 1024:
        size_str = f"{total_size / (1024 * 1024):.0f} MB"
    else:
        size_str = f"{total_size / (1024 * 1024 * 1024):.1f} GB"

    print(f"\n  {len(files)} files to index ({size_str}):")
    category_order = [
        "PDFs", "Images", "Office", "HTML", "Code", "Text", "Data",
        "Videos", "Audio", "Archives", "Installers/Apps", "Fonts",
        "System/Meta", "Other",
    ]
    for cat in category_order:
        if cat in cats:
            print(f"    {cat:18s}  {cats[cat]:>4}")


def _ingest_real_files(
    files: list[_Path],
    root: _Path | None = None,
) -> tuple[dict[str, int], dict[str, str]]:
    """Extract and ingest ALL files via the dispatcher.

    Files that can't be fully extracted still get indexed with rich metadata
    (name, type, size, extension) so the system knows they exist.

    Returns (counts, id_to_name).
    """
    import asyncio as _aio
    import hashlib
    import time
    from services.embedding import pipeline
    from services.file_processor.dispatcher import extract as dispatch_extract
    from services.file_processor.models import ContentResult

    counts: dict[str, int] = {}
    id_to_name: dict[str, str] = {}
    errors_list: list[str] = []
    metadata_count = 0
    total = len(files)
    start = time.time()

    for idx, fpath in enumerate(files, 1):
        rel = fpath.relative_to(root) if root and fpath.is_relative_to(root) else fpath.name
        display = str(rel)
        file_id = hashlib.sha256(str(fpath).encode()).hexdigest()[:16]
        id_to_name[file_id] = display

        # Progress with ETA
        elapsed = time.time() - start
        if idx > 5 and elapsed > 0:
            rate = idx / elapsed
            remaining = (total - idx) / rate
            eta = f"  ~{remaining:.0f}s left" if remaining > 5 else ""
        else:
            eta = ""

        short_name = display[:55] if len(display) <= 55 else "..." + display[-52:]
        print(f"    [{idx:>4}/{total}] {short_name}", end="", flush=True)

        try:
            # ── .app bundles (directories) — metadata only ────────────
            if fpath.is_dir():
                meta_text = _file_metadata_description(fpath)
                cr = ContentResult(
                    filename=fpath.name, file_name=fpath.name,
                    mime_type="application/x-apple-app",
                    category="application",
                    content=meta_text, text=meta_text,
                    engine_used="metadata", fallback_used=False, errors=[],
                )
                res = pipeline.ingest(cr, file_id)
                counts[file_id] = res.chunk_count
                metadata_count += 1
                print(f"  → metadata [app bundle]{eta}")
                continue

            # ── Size check for Gemini-bound media ─────────────────────
            try:
                size_mb = fpath.stat().st_size / (1024 * 1024)
            except OSError:
                size_mb = 0

            ext = fpath.suffix.lower()

            # Files too large for Gemini API — index with metadata
            from services.file_processor.dispatcher import (
                GEMINI_MIME_TYPES, TEXT_LIKE_EXTENSIONS,
                OFFICE_MIME_TYPES, ARCHIVE_MIME_TYPES,
            )
            needs_gemini = (ext in GEMINI_MIME_TYPES and ext not in TEXT_LIKE_EXTENSIONS
                           and ext not in OFFICE_MIME_TYPES and ext not in ARCHIVE_MIME_TYPES)

            if needs_gemini and size_mb > MAX_GEMINI_FILE_SIZE_MB:
                meta_text = _file_metadata_description(fpath)
                cr = ContentResult(
                    filename=fpath.name, file_name=fpath.name,
                    mime_type=GEMINI_MIME_TYPES.get(ext, "application/octet-stream"),
                    category="media",
                    content=meta_text, text=meta_text,
                    engine_used="metadata", fallback_used=False, errors=[],
                )
                res = pipeline.ingest(cr, file_id)
                counts[file_id] = res.chunk_count
                metadata_count += 1
                print(f"  → metadata [{size_mb:.0f}MB, too large for API]{eta}")
                continue

            # ── Normal extraction ─────────────────────────────────────
            file_bytes = fpath.read_bytes()
            cr = _aio.run(dispatch_extract(file_bytes, fpath.name))

            if not cr.content or not cr.content.strip():
                # Extraction returned empty — use metadata instead
                meta_text = _file_metadata_description(fpath)
                cr = ContentResult(
                    filename=fpath.name, file_name=fpath.name,
                    mime_type=cr.mime_type or "application/octet-stream",
                    category=cr.category or "unknown",
                    content=meta_text, text=meta_text,
                    engine_used="metadata", fallback_used=False, errors=[],
                )
                res = pipeline.ingest(cr, file_id)
                counts[file_id] = res.chunk_count
                metadata_count += 1
                print(f"  → metadata [empty extraction]{eta}")
                continue

            res = pipeline.ingest(cr, file_id)
            counts[file_id] = res.chunk_count
            print(f"  → {res.chunk_count} chunks [{cr.engine_used}]{eta}")

        except Exception as exc:
            # Even on errors — index with metadata so we know it exists
            short_err = str(exc)[:60]
            try:
                meta_text = _file_metadata_description(fpath)
                cr = ContentResult(
                    filename=fpath.name, file_name=fpath.name,
                    mime_type="application/octet-stream",
                    category="unknown",
                    content=meta_text, text=meta_text,
                    engine_used="metadata", fallback_used=False, errors=[],
                )
                res = pipeline.ingest(cr, file_id)
                counts[file_id] = res.chunk_count
                metadata_count += 1
                print(f"  → metadata [error: {short_err}]{eta}")
            except Exception:
                print(f"  → FAILED: {short_err}{eta}")
                errors_list.append(f"{display}: {short_err}")

    elapsed = time.time() - start
    total_indexed = sum(1 for c in counts.values() if c > 0)
    print(f"\n  Ingestion complete in {elapsed:.1f}s")
    print(f"  {total_indexed} files indexed, {metadata_count} via metadata-only")
    if errors_list:
        print(f"  {len(errors_list)} file(s) completely failed")

    return counts, id_to_name


def run_interactive(
    user_files: list[str] | None = None,
    user_dir: str | None = None,
) -> None:
    print("\n" + "=" * 64)
    print("WISP — Interactive File Memory")
    print("=" * 64)

    if not _require_api_key():
        return

    from services.embedding import pipeline, store

    tmp = _create_temp_store()
    id_to_name: dict[str, str] = {}

    try:
        # ── Determine what to ingest ──────────────────────────────────
        if user_dir:
            root = _Path(user_dir).resolve()
            print(f"\n  Scanning {root} ...")
            files = _collect_files_from_dir(user_dir)
            if not files:
                print("  No files found.")
                return
            _print_scan_summary(files, root)
            print(f"\n  Ingesting ALL files...\n")
            counts, id_to_name = _ingest_real_files(files, root=root)
        elif user_files:
            files = _resolve_file_list(user_files)
            if not files:
                print("  No valid files to ingest.")
                return
            print(f"\n  Ingesting {len(files)} file(s)...\n")
            counts, id_to_name = _ingest_real_files(files)
        else:
            print("\n  Ingesting 3 built-in demo documents...")
            counts = _ingest_test_docs()
            id_to_name = {fid: doc["filename"] for fid, doc in DOCS.items()}

        total_chunks = store.collection_count()
        indexed = sum(1 for c in counts.values() if c > 0)
        print(f"\n  ✓ {indexed} file(s) in memory, {total_chunks} chunks total.")

        print("\n  Ask anything about these files.  Type 'quit' to exit.\n")

        # ── Query loop ────────────────────────────────────────────────
        while True:
            try:
                query = input("  wisp> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not query or query.lower() in ("quit", "exit", "q"):
                break

            print("  thinking...\n")
            result = pipeline.ask(query, k=8)

            # ── AI Answer ─────────────────────────────────────────────
            width = min(shutil.get_terminal_size().columns - 6, 78)
            border = "─" * (width - 2)
            print(f"  ┌{border}┐")
            for line in result.answer.splitlines():
                for wrapped in textwrap.wrap(line, width=width - 4) or [""]:
                    pad = " " * (width - 2 - len(wrapped))
                    print(f"  │ {wrapped}{pad}│")
            print(f"  └{border}┘")

            # ── Sources ───────────────────────────────────────────────
            if result.hits:
                seen: set[str] = set()
                sources: list[str] = []
                for h in result.hits:
                    label = id_to_name.get(h.file_id, h.file_path or h.file_id)
                    if label not in seen:
                        seen.add(label)
                        sources.append(label)
                print(f"  sources: {', '.join(sources)}")
            print()

    finally:
        pipeline.teardown_store()
        shutil.rmtree(tmp, ignore_errors=True)
        print("  (cleaned up temp index)")


# ═══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_path_args(flag: str) -> list[str]:
    """Extract paths following a flag (--files or --dir) from sys.argv."""
    if flag not in sys.argv:
        return []
    idx = sys.argv.index(flag) + 1
    paths: list[str] = []
    while idx < len(sys.argv) and not sys.argv[idx].startswith("-"):
        paths.append(sys.argv[idx])
        idx += 1
    return paths


def main() -> None:
    interactive = "--interactive" in sys.argv or "-i" in sys.argv

    print("\n╔════════════════════════════════════════╗")
    print("║  WISP — Embedding Pipeline Test Suite  ║")
    print("╚════════════════════════════════════════╝")

    if interactive:
        user_files = _parse_path_args("--files")
        dir_args = _parse_path_args("--dir")
        user_dir = dir_args[0] if dir_args else None
        run_interactive(user_files=user_files or None, user_dir=user_dir)
    else:
        run_chunker_tests()
        run_pipeline_tests()

        total = _pass_count + _fail_count
        print("\n" + "=" * 64)
        print(f"  Results: {_pass_count}/{total} passed", end="")
        if _fail_count:
            print(f"  — {_fail_count} FAILED")
        else:
            print("  — all good")
        print("=" * 64 + "\n")

        sys.exit(0 if _fail_count == 0 else 1)


if __name__ == "__main__":
    main()

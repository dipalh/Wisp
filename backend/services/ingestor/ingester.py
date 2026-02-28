"""
File ingestion orchestrator for the Wisp pipeline.

Bridges path-on-disk → ContentResult → embedding pipeline.
Applies a RAM safety cap before reading file bytes, then delegates
content extraction to the dispatcher (which handles its own 8 MB
Gemini threshold internally).

Public surface
--------------
  ingest_file(fp, display_path, pipeline) -> str
  ingest_directory(root, *, memory_cap_mb, progress_cb) -> int
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

# Files larger than this are never read into RAM — filename inference is used directly.
# The dispatcher also has its own 8 MB threshold for Gemini-bound binaries that ARE
# read into memory (for files in the 8–100 MB range).
MEMORY_CAP_MB = 100


async def ingest_file(fp: Path, display_path: str, pipeline) -> str:
    """Ingest a single file into the embedding pipeline.

    Args:
        fp:           Absolute path to the file on disk.
        display_path: Relative path string used as the stored file_path.
        pipeline:     The embedding pipeline module (services.embedding.pipeline).

    Returns:
        The engine_used string (e.g. "gemini", "local", "filename-infer").

    Raises:
        Any exception from the dispatcher or embedding pipeline propagates up
        so the caller can log and continue.
    """
    from services.file_processor.dispatcher import extract as dispatch_extract
    from services.file_processor.models import ContentResult

    file_id = hashlib.sha256(str(fp).encode()).hexdigest()[:16]
    size_mb = fp.stat().st_size / (1024 * 1024)

    if size_mb > MEMORY_CAP_MB:
        # Too large to safely read into RAM — infer meaning from filename only.
        from ai.generate import infer_from_filename
        description = await infer_from_filename(fp.name)
        cr = ContentResult(
            filename=display_path,
            file_name=display_path,
            mime_type="application/octet-stream",
            category="other",
            content=description,
            text=description,
            engine_used="filename-infer",
        )
        pipeline.ingest(cr, file_id)
        return f"filename-infer ({size_mb:.0f} MB, over memory cap)"

    # Under MEMORY_CAP_MB: read bytes and let the dispatcher decide.
    # Dispatcher applies its own 8 MB threshold for Gemini-bound binaries.
    file_bytes = fp.read_bytes()
    cr = await dispatch_extract(file_bytes, fp.name)
    # Store with the display path (relative) rather than the raw filename.
    cr.filename = display_path
    cr.file_name = display_path
    pipeline.ingest(cr, file_id)
    return cr.engine_used


async def ingest_directory(
    root: Path,
    *,
    memory_cap_mb: int = MEMORY_CAP_MB,
    progress_cb: Callable[[int, int, str, str], None] | None = None,
    classify: bool = False,
) -> int:
    """Scan *root* and ingest every file into the embedding pipeline.

    Args:
        root:          Directory to scan and ingest.
        memory_cap_mb: Override the RAM cap (default: MEMORY_CAP_MB).
        progress_cb:   Optional callback invoked after each file:
                       progress_cb(idx, total, display_path, engine_result)
        classify:      If True, classify each file after ingesting and move it
                       into root/<Category>/ or root/Unsorted/.

    Returns:
        Number of files successfully processed (errors are skipped).
    """
    from services.embedding import pipeline
    from services.ingestor.scanner import collect_files

    files = collect_files(root)
    total = len(files)
    processed = 0

    for idx, fp in enumerate(files, 1):
        try:
            rel = fp.relative_to(root) if fp.is_relative_to(root) else Path(fp.name)
            display = str(rel)
        except ValueError:
            display = fp.name

        try:
            engine_result = await ingest_file(fp, display, pipeline)
            processed += 1
            if classify:
                file_id = hashlib.sha256(str(fp).encode()).hexdigest()[:16]
                from services.classifier import classify_file
                try:
                    cr = await classify_file(fp, file_id, root)
                    engine_result += f" → {cr.category} ({cr.confidence:.0%})"
                except Exception as ce:
                    engine_result += f" [classify error: {ce}]"
        except Exception as exc:
            engine_result = f"ERROR: {exc}"

        if progress_cb is not None:
            progress_cb(idx, total, display, engine_result)

    return processed

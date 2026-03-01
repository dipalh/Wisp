"""
Celery scan tasks — real embedding pipeline + lightweight dummy for tests.

scan_and_index(job_id, folder_paths)
    Walks the given folders, calls pipeline.ingest_file() for each file,
    records progress in the jobs table, and upserts results into the
    indexed_files table.

dummy_scan(job_id)
    50-step sleep loop for smoke-testing the job spine without real I/O.
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import logging
import sys
import time
import traceback
from pathlib import Path

_backend_dir = str(Path(__file__).resolve().parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

from celery_app import app
from services.job_db import (
    set_status,
    update_progress,
    upsert_indexed_file,
)

logger = logging.getLogger("wisp.tasks.scan")


# ── Real scan task ────────────────────────────────────────────────────


async def _run_pipeline(job_id: str, all_files: list[Path]) -> int:
    """Async inner loop: init store → ingest each file → teardown.

    Returns the count of successfully indexed files.
    """
    import sys as _sys
    _bd = str(Path(__file__).resolve().parent.parent)
    if _bd not in _sys.path:
        _sys.path.insert(0, _bd)

    from services.embedding import pipeline
    from services.os_tags.deletable import should_mark_deletable, set_deletable

    total = len(all_files)
    indexed = 0

    pipeline.init_store()
    try:
        for i, file_path in enumerate(all_files):
            filename = file_path.name
            ext = file_path.suffix.lower()

            update_progress(job_id, i, total, f"Indexing: {filename}")

            try:
                result = await pipeline.ingest_file(file_path)
            except Exception as exc:
                logger.warning("ingest_file failed for %s: %s", file_path, exc)
                continue

            # is_deletable: heuristic decision (DB source of truth for UI/tinder).
            is_del = False
            try:
                is_del = should_mark_deletable(file_path, ext, result.depth)
            except Exception:
                pass

            # os_tag_applied: True only when we successfully wrote the
            # "Deletable" OS tag.  When is_del is False we still call
            # set_deletable(path, False) to clean up stale tags, but
            # os_tag_applied stays False (we didn't *apply* a tag).
            os_tag_applied = False
            try:
                tag_write_ok = set_deletable(file_path, is_del)
                if is_del and tag_write_ok:
                    os_tag_applied = True
            except Exception:
                pass

            try:
                upsert_indexed_file(
                    file_id=result.file_id,
                    job_id=job_id,
                    file_path=str(file_path),
                    name=filename,
                    ext=ext,
                    depth=result.depth,
                    chunk_count=result.chunk_count,
                    engine=result.engine,
                    is_deletable=is_del,
                    tagged_os=os_tag_applied,
                )
            except Exception as exc:
                logger.warning("upsert_indexed_file failed for %s: %s", file_path, exc)

            indexed += 1
            update_progress(job_id, i + 1, total, f"Indexed: {filename}")
    finally:
        pipeline.teardown_store()

    return indexed


@app.task(name="tasks.scan_and_index")
def scan_and_index(job_id: str, folder_paths: list[str]) -> None:
    """Walk folders, embed every file via the 3-layer pipeline, track progress."""
    try:
        from services.ingestor.scanner import collect_files

        set_status(job_id, "running")
        update_progress(job_id, 0, 0, "Enumerating files\u2026")

        all_files: list[Path] = []
        for folder in folder_paths:
            root = Path(folder)
            if root.is_dir():
                all_files.extend(collect_files(root))

        total = len(all_files)
        if total == 0:
            set_status(job_id, "success", "No files found in the selected folders")
            return

        update_progress(job_id, 0, total, f"Found {total} files \u2014 starting\u2026")

        # Run the async pipeline in a dedicated thread so it always gets a
        # clean event loop — even when Celery eager mode executes inside
        # FastAPI's existing async context (tests).
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            indexed = pool.submit(asyncio.run, _run_pipeline(job_id, all_files)).result()

        set_status(
            job_id, "success",
            f"Scan complete \u2014 {indexed}/{total} files indexed",
        )
    except Exception:
        set_status(job_id, "failed", traceback.format_exc(limit=3))


# ── Dummy task (kept for smoke tests) ─────────────────────────────────


@app.task(name="tasks.dummy_scan")
def dummy_scan(job_id: str) -> None:
    """Simulate a long-running scan job (50 × 0.2 s)."""
    try:
        set_status(job_id, "running")
        total = 50
        for i in range(total):
            time.sleep(0.2)
            update_progress(job_id, i + 1, total, f"Processing file {i + 1}")
        set_status(job_id, "success", "Scan complete")
    except Exception:
        set_status(job_id, "failed", traceback.format_exc(limit=3))

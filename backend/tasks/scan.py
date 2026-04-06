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
import hashlib
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
    get_job,
    reconcile_indexed_files,
    set_status,
    update_progress,
    upsert_indexed_file,
)
from services.scan_progress import ScanProgressTracker

logger = logging.getLogger("wisp.tasks.scan")

SCAN_BATCH_SIZE = 4
SCAN_MAX_CONCURRENT_FILES = 4
SCAN_PROGRESS_CADENCE_FILES = 0


# ── Real scan task ────────────────────────────────────────────────────


async def _run_pipeline(
    job_id: str,
    all_files: list[Path],
    tracker: ScanProgressTracker,
) -> int:
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
    file_sem = asyncio.Semaphore(max(1, int(SCAN_MAX_CONCURRENT_FILES)))

    async def _process_one(file_path: Path) -> tuple[Path, object | None, str | None]:
        """Ingest a single file. Returns (path, result, error_message)."""
        filename = file_path.name
        ext = file_path.suffix.lower()

        async with file_sem:
            try:
                result = await pipeline.ingest_file(file_path)
            except Exception as exc:
                logger.warning("ingest_file failed for %s: %s", file_path, exc)
                return file_path, None, str(exc)

        is_del = False
        try:
            is_del = should_mark_deletable(file_path, ext, result.depth)
        except Exception:
            pass

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
            return file_path, None, str(exc)

        return file_path, result, None

    pipeline.init_store()
    try:
        for batch_start in range(0, total, SCAN_BATCH_SIZE):
            batch = all_files[batch_start:batch_start + SCAN_BATCH_SIZE]
            batch_names = ", ".join(f.name for f in batch)
            update_progress(job_id, batch_start, total, f"Indexing: {batch_names}")

            results = await asyncio.gather(
                *[_process_one(fp) for fp in batch],
                return_exceptions=True,
            )
            for outcome in results:
                if isinstance(outcome, Exception):
                    tracker.record_failure(batch[0], str(outcome))
                    continue
                file_path, result, error_message = outcome
                if result is not None:
                    tracker.record_metadata(file_path)
                    indexed += 1
                    tracker.record_result(
                        file_path,
                        depth=result.depth,
                        skipped=result.skipped,
                    )
                else:
                    tracker.record_failure(file_path, error_message or "unknown failure")
    finally:
        pipeline.teardown_store()

    return indexed


@app.task(name="tasks.scan_and_index")
def scan_and_index(job_id: str, folder_paths: list[str]) -> None:
    """Walk folders, embed every file via the 3-layer pipeline, track progress."""
    try:
        from services.ingestor.scanner import ScanIssue, collect_scan_report

        set_status(job_id, "running")
        update_progress(job_id, 0, 0, "Enumerating files\u2026")

        all_files: list[Path] = []
        scan_issues = []
        scanned_roots: list[str] = []
        for folder in folder_paths:
            root = Path(folder)
            if root.is_dir():
                scanned_roots.append(str(root.resolve()))
                files, issues = collect_scan_report(root)
                all_files.extend(files)
                scan_issues.extend(issues)
            else:
                scan_issues.append(
                    ScanIssue(
                        path=root,
                        file_state="MISSING_EXTERNALLY",
                        error_code="MISSING_EXTERNALLY",
                        error_message="Scan root unavailable or not a directory.",
                    )
                )

        total = len(all_files)
        tracker = ScanProgressTracker(
            job_id,
            update_progress,
            progress_cadence_files=SCAN_PROGRESS_CADENCE_FILES,
        )
        tracker.begin(total + len(scan_issues))

        indexed = 0
        if total > 0:
            # Run the async pipeline in a dedicated thread so it always gets a
            # clean event loop — even when Celery eager mode executes inside
            # FastAPI's existing async context (tests).
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                indexed = pool.submit(asyncio.run, _run_pipeline(job_id, all_files, tracker)).result()

        for issue in scan_issues:
            upsert_indexed_file(
                file_id=hashlib.sha256(f"scan-issue:{issue.path}".encode()).hexdigest()[:16],
                job_id=job_id,
                file_path=str(issue.path),
                name=issue.path.name,
                ext=issue.path.suffix.lower(),
                depth="card",
                chunk_count=0,
                engine="scanner",
                is_deletable=False,
                tagged_os=False,
                file_state=issue.file_state,
                fingerprint="",
                error_code=issue.error_code,
                error_message=issue.error_message,
            )
            tracker.record_issue(issue.path, issue.error_message)
        reconcile_indexed_files(job_id, scanned_roots)
        if total == 0:
            update_progress(
                job_id,
                0,
                0,
                "No files found during discovery",
                stage="SCORED",
                stats={
                    "discovered": 0,
                    "previewed": 0,
                    "embedded": 0,
                    "scored": 0,
                    "cached": 0,
                    "failed": 0,
                },
            )
            if scan_issues:
                set_status(
                    job_id,
                    "success",
                    f"No indexable files found; recorded {len(scan_issues)} root/path issue(s).",
                )
            else:
                set_status(job_id, "success", "No files found in the selected folders")
            return
        set_status(
            job_id, "success",
            f"Scan complete \u2014 {indexed}/{total} files indexed",
        )
    except Exception:
        failure_message = traceback.format_exc(limit=3)
        job = get_job(job_id) or {}
        stats = dict(job.get("stats", {}))
        stats.setdefault("discovered", 0)
        stats.setdefault("previewed", 0)
        stats.setdefault("embedded", 0)
        stats.setdefault("scored", 0)
        stats.setdefault("cached", 0)
        stats["failed"] = int(stats.get("failed", 0)) + 1
        update_progress(
            job_id,
            int(job.get("progress_current", 0)),
            int(job.get("progress_total", 0)),
            failure_message,
            stage=job.get("stage", "DISCOVERED") or "DISCOVERED",
            stats=stats,
        )
        set_status(job_id, "failed", failure_message)


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

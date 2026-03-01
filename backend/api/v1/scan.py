"""
Scan / Index API — Flow 1 entry points.

Routes
------
  POST  /api/v1/scan               Start a background scan+index job
  GET   /api/v1/scan/status        Poll job progress
  GET   /api/v1/candidates         Retrieve junk candidates from a completed job

Flow
----
  1. Client POSTs a directory path.
  2. Server validates the path and creates a Job (PENDING).
  3. Background task runs:
       - collect_files()
       - pipeline.ingest_file() per file  (embedding pipeline)
       - heuristics.score_file() per file (inline, no extra I/O)
       - Job transitions RUNNING -> DONE | FAILED
  4. Client polls GET /scan/status?job_id=... until status == "done".
  5. Client calls GET /candidates?job_id=... to retrieve scored files.
"""
from __future__ import annotations

import asyncio
import traceback
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException

import services.jobs as job_store
import services.roots as roots_store
from services.heuristics import score_file
from services.ingestor.scanner import collect_files
from services.jobs import JobStatus

router = APIRouter()


# ── POST /scan ────────────────────────────────────────────────────────────────


@router.post("", summary="Start a scan+index job for a directory")
async def start_scan(path: str, background_tasks: BackgroundTasks):
    """Kick off a background scan of *path*.

    - Validates that *path* is a directory.
    - Checks the Root Scope Guard (if any roots are registered, *path* must
      be under one of them).
    - Creates a Job and immediately returns its id so the client can poll.

    Returns:
        job_id, status
    """
    root = Path(path)

    if not root.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    if not roots_store.is_under_root(str(root)):
        raise HTTPException(
            status_code=403,
            detail=f"Path is not under any registered root: {path}",
        )

    job = job_store.create_job(str(root))
    background_tasks.add_task(_run_scan, job.id, root)
    return {"job_id": job.id, "status": job.status}


# ── GET /scan/status ──────────────────────────────────────────────────────────


@router.get("/status", summary="Poll the status of a scan job")
async def scan_status(job_id: str):
    """Return current progress for *job_id*.

    Returns:
        job_id, status, processed, total, errors, root
    """
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return {
        "job_id":    job.id,
        "status":    job.status,
        "processed": job.processed,
        "total":     job.total,
        "errors":    job.errors,
        "root":      job.root,
    }


# ── GET /candidates ───────────────────────────────────────────────────────────


@router.get("/candidates", summary="Retrieve junk candidates from a scan job")
async def get_candidates(job_id: str, min_score: float = 0.35):
    """Return files scored above *min_score* for the given job.

    Results are sorted descending by junk_score (worst junk first).

    Args:
        job_id:    ID returned by POST /scan.
        min_score: Only include candidates at or above this score (default 0.35).

    Returns:
        candidates[], total
    """
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    candidates = [c for c in job.candidates if c["junk_score"] >= min_score]
    candidates.sort(key=lambda c: c["junk_score"], reverse=True)
    return {"candidates": candidates, "total": len(candidates)}


# ── Background task ───────────────────────────────────────────────────────────


async def _run_scan(job_id: str, root: Path) -> None:
    """Background coroutine: collect -> embed -> score -> update job."""
    job_store.update_job(job_id, status=JobStatus.RUNNING)
    try:
        files = collect_files(root)
        job_store.update_job(job_id, total=len(files))

        from services.embedding import pipeline  # lazy import keeps startup fast

        candidates: list[dict] = []
        errors = 0

        for idx, fp in enumerate(files):
            try:
                # Embed the file (3-layer smart pipeline — skips cached files)
                await pipeline.ingest_file(fp)
            except Exception:
                errors += 1

            # Score from metadata regardless of embed outcome
            scored = score_file(fp)
            if scored["junk_score"] > 0:
                candidates.append(scored)

            # Flush progress every file so the client sees smooth updates
            job_store.update_job(job_id, processed=idx + 1, errors=errors)

        job_store.update_job(
            job_id,
            status=JobStatus.DONE,
            candidates=candidates,
            errors=errors,
        )

    except Exception:
        job_store.update_job(
            job_id,
            status=JobStatus.FAILED,
            error_msg=traceback.format_exc(limit=5),
        )

"""
Job management API — trigger and poll long-running Celery tasks.

Routes
------
  POST /api/v1/jobs/scan              Start a scan-and-index job
  GET  /api/v1/jobs/indexed-files     List indexed files (optional ?job_id= filter)
  GET  /api/v1/jobs/{job_id}          Poll job progress
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from services.job_db import create_job, get_job, get_indexed_files
from tasks.scan import scan_and_index

router = APIRouter()


class ScanRequest(BaseModel):
    folders: list[str]


@router.post("/scan", summary="Start a scan & index job")
async def start_scan_job(body: ScanRequest, background_tasks: BackgroundTasks):
    """Create a queued job and run scan_and_index as a background task."""
    if not body.folders:
        raise HTTPException(status_code=400, detail="folders list must not be empty")
    job_id = uuid.uuid4().hex
    create_job(job_id, "scan")
    background_tasks.add_task(scan_and_index, job_id, body.folders)
    return {"job_id": job_id}


@router.get("/indexed-files", summary="List indexed files")
async def list_indexed_files(job_id: Optional[str] = None, limit: int = 500):
    """Return indexed_files rows, optionally filtered by job_id."""
    rows = get_indexed_files(job_id=job_id, limit=limit)
    return {"files": rows, "total": len(rows)}


@router.get("/{job_id}", summary="Poll job progress")
async def poll_job(job_id: str):
    """Return current status and progress for a job."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return {
        "job_id":           job["job_id"],
        "type":             job["type"],
        "status":           job["status"],
        "progress_current": job["progress_current"],
        "progress_total":   job["progress_total"],
        "progress_message": job["progress_message"],
        "updated_at":       job["updated_at"],
    }

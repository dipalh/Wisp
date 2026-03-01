"""
Job management API — trigger and poll long-running Celery tasks.

Routes
------
  POST /api/v1/jobs/scan       Start a dummy scan job
  GET  /api/v1/jobs/{job_id}   Poll job progress
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from services.job_db import create_job, get_job
from tasks.scan import dummy_scan

router = APIRouter()


@router.post("/scan", summary="Start a scan job (dummy)")
async def start_scan_job():
    """Create a queued job and dispatch the dummy scan task via Celery."""
    job_id = uuid.uuid4().hex
    create_job(job_id, "scan")
    dummy_scan.delay(job_id)
    return {"job_id": job_id}


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

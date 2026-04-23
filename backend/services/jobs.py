"""
In-memory scan job manager.

Legacy note
-----------
This module backs the legacy ``api/v1/scan.py`` flow and is not the canonical
runtime job store for the live app. The production scan/index path uses the
SQLite-backed ``services.job_db`` plus Celery task execution.

Tracks the lifecycle of a background scan job from creation through
completion.  Session-scoped — resets when the server restarts, which
is acceptable for a single-user desktop app.

Public API
----------
  create_job(root)              -> Job
  get_job(job_id)               -> Job | None
  list_jobs()                   -> list[Job]
  update_job(job_id, **fields)  -> None
  clear()                       -> None

Job lifecycle
-------------
  PENDING  -> RUNNING  -> DONE
                       -> FAILED
"""
from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from enum import Enum


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE    = "done"
    FAILED  = "failed"


@dataclass
class Job:
    id:         str
    root:       str
    status:     JobStatus      = JobStatus.PENDING
    total:      int            = 0
    processed:  int            = 0
    errors:     int            = 0
    # Heuristics results computed inline during the scan.
    # Each entry is a dict from heuristics.score_file().
    candidates: list[dict]     = field(default_factory=list)
    error_msg:  str            = ""


_lock  = threading.Lock()
_jobs: dict[str, Job] = {}


def create_job(root: str) -> Job:
    """Create and register a new PENDING job for *root*."""
    job_id = uuid.uuid4().hex[:8]
    job = Job(id=job_id, root=root)
    with _lock:
        _jobs[job_id] = job
    return job


def get_job(job_id: str) -> Job | None:
    """Return the job with *job_id*, or None if not found."""
    return _jobs.get(job_id)


def list_jobs() -> list[Job]:
    """Return all jobs, most-recently created last."""
    with _lock:
        return list(_jobs.values())


def update_job(job_id: str, **fields) -> None:
    """Update arbitrary fields on an existing job.

    Silently ignores unknown job ids (prevents crashes in background tasks
    that might outlive test teardown).
    """
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return
        for key, val in fields.items():
            if hasattr(job, key):
                setattr(job, key, val)


def clear() -> None:
    """Remove all jobs (useful for tests)."""
    with _lock:
        _jobs.clear()

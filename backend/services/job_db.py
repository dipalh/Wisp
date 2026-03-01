"""
SQLite-backed job store for long-running Celery tasks.

Database: wisp_jobs.db (created next to this file, inside backend/services/)

Public API
----------
  ensure_table()                            -> None
  create_job(job_id, job_type)              -> None
  get_job(job_id)                           -> dict | None
  update_progress(job_id, current, total, message) -> None
  set_status(job_id, status, message="")    -> None
"""
from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parent.parent / "wisp_jobs.db"
_local = threading.local()


def _conn() -> sqlite3.Connection:
    """Return a per-thread SQLite connection (thread-safe)."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(_DB_PATH), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        _local.conn = conn
    return conn


def ensure_table() -> None:
    """Create the jobs table if it doesn't exist (idempotent)."""
    _conn().execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            job_id           TEXT PRIMARY KEY,
            type             TEXT NOT NULL,
            status           TEXT NOT NULL DEFAULT 'queued',
            progress_current INTEGER NOT NULL DEFAULT 0,
            progress_total   INTEGER NOT NULL DEFAULT 0,
            progress_message TEXT NOT NULL DEFAULT '',
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL
        )
    """)
    _conn().commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_job(job_id: str, job_type: str) -> None:
    """Insert a new job row with status='queued'."""
    now = _now()
    _conn().execute(
        """
        INSERT INTO jobs (job_id, type, status, progress_current, progress_total,
                          progress_message, created_at, updated_at)
        VALUES (?, ?, 'queued', 0, 0, '', ?, ?)
        """,
        (job_id, job_type, now, now),
    )
    _conn().commit()


def get_job(job_id: str) -> dict | None:
    """Return full job row as a dict, or None if not found."""
    row = _conn().execute(
        "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def update_progress(
    job_id: str, current: int, total: int, message: str
) -> None:
    """Update progress fields + updated_at."""
    _conn().execute(
        """
        UPDATE jobs
        SET progress_current = ?,
            progress_total   = ?,
            progress_message = ?,
            updated_at       = ?
        WHERE job_id = ?
        """,
        (current, total, message, _now(), job_id),
    )
    _conn().commit()


def set_status(job_id: str, status: str, message: str = "") -> None:
    """Update status (and optionally progress_message) + updated_at."""
    if message:
        _conn().execute(
            """
            UPDATE jobs
            SET status           = ?,
                progress_message = ?,
                updated_at       = ?
            WHERE job_id = ?
            """,
            (status, message, _now(), job_id),
        )
    else:
        _conn().execute(
            """
            UPDATE jobs
            SET status     = ?,
                updated_at = ?
            WHERE job_id = ?
            """,
            (status, _now(), job_id),
        )
    _conn().commit()


# Auto-create table on import
ensure_table()

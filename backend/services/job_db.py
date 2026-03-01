"""
SQLite-backed job store for long-running Celery tasks.

Database: wisp_jobs.db (created in the backend/ directory)

Connection policy
-----------------
  Every public function opens a fresh connection and closes it before
  returning.  This is safe when FastAPI (async thread-pool) and Celery
  workers (separate processes) both write concurrently.

  WAL mode is enabled so readers never block writers.

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
from datetime import datetime, timezone
from pathlib import Path

_DB_PATH = Path(__file__).resolve().parent.parent / "wisp_jobs.db"


def _db_path() -> str:
    """Return the database path as a string.  Indirection allows tests
    to monkey-patch ``_DB_PATH``."""
    return str(_DB_PATH)


def _connect() -> sqlite3.Connection:
    """Open a **new** connection with WAL mode and row_factory."""
    conn = sqlite3.connect(_db_path(), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Schema ────────────────────────────────────────────────────────────


def ensure_table() -> None:
    """Create the jobs table if it doesn't exist (idempotent)."""
    conn = _connect()
    try:
        conn.execute("""
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
        conn.commit()
    finally:
        conn.close()


# ── CRUD ──────────────────────────────────────────────────────────────


def create_job(job_id: str, job_type: str) -> None:
    """Insert a new job row with status='queued'."""
    now = _now()
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO jobs (job_id, type, status, progress_current, progress_total,
                              progress_message, created_at, updated_at)
            VALUES (?, ?, 'queued', 0, 0, '', ?, ?)
            """,
            (job_id, job_type, now, now),
        )
        conn.commit()
    finally:
        conn.close()


def get_job(job_id: str) -> dict | None:
    """Return full job row as a dict, or None if not found."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        return dict(row)
    finally:
        conn.close()


def update_progress(
    job_id: str, current: int, total: int, message: str
) -> None:
    """Update progress fields + updated_at."""
    conn = _connect()
    try:
        conn.execute(
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
        conn.commit()
    finally:
        conn.close()


def set_status(job_id: str, status: str, message: str = "") -> None:
    """Update status (and optionally progress_message) + updated_at."""
    conn = _connect()
    try:
        if message:
            conn.execute(
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
            conn.execute(
                """
                UPDATE jobs
                SET status     = ?,
                    updated_at = ?
                WHERE job_id = ?
                """,
                (status, _now(), job_id),
            )
        conn.commit()
    finally:
        conn.close()


# Auto-create table on import
ensure_table()

"""
SQLite-backed job store for long-running Celery tasks.

Database: wisp_jobs.db (created in the backend/ directory)

Connection policy
-----------------
  Every public function opens a fresh connection and closes it before
  returning.  This is safe when FastAPI (async thread-pool) and Celery
  workers (separate processes) both write concurrently.

  WAL mode is enabled so readers never block writers.

Public API — jobs
-----------------
  ensure_table()                            -> None
  create_job(job_id, job_type)              -> None
  get_job(job_id)                           -> dict | None
  update_progress(job_id, current, total, message) -> None
  set_status(job_id, status, message="")    -> None

Public API — indexed_files
--------------------------
  ensure_indexed_files_table()              -> None
  upsert_indexed_file(...)                  -> None
  get_indexed_files(job_id, limit)          -> list[dict]
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


# ── indexed_files schema ──────────────────────────────────────────────


def ensure_indexed_files_table() -> None:
    """Create the indexed_files table if it doesn't exist (idempotent)."""
    conn = _connect()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS indexed_files (
                file_id      TEXT PRIMARY KEY,
                job_id       TEXT NOT NULL,
                file_path    TEXT NOT NULL,
                name         TEXT NOT NULL,
                ext          TEXT NOT NULL DEFAULT '',
                depth        TEXT NOT NULL DEFAULT 'card',
                chunk_count  INTEGER NOT NULL DEFAULT 0,
                engine       TEXT NOT NULL DEFAULT '',
                is_deletable INTEGER NOT NULL DEFAULT 0,
                tagged_os    INTEGER NOT NULL DEFAULT 0,
                updated_at   TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


# ── indexed_files CRUD ────────────────────────────────────────────────


def upsert_indexed_file(
    file_id: str,
    job_id: str,
    file_path: str,
    name: str,
    ext: str,
    depth: str,
    chunk_count: int,
    engine: str,
    is_deletable: bool,
    tagged_os: bool,
) -> None:
    """Insert or update an indexed_files row."""
    conn = _connect()
    try:
        conn.execute(
            """
            INSERT INTO indexed_files
                (file_id, job_id, file_path, name, ext, depth,
                 chunk_count, engine, is_deletable, tagged_os, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_id) DO UPDATE SET
                job_id       = excluded.job_id,
                file_path    = excluded.file_path,
                name         = excluded.name,
                ext          = excluded.ext,
                depth        = excluded.depth,
                chunk_count  = excluded.chunk_count,
                engine       = excluded.engine,
                is_deletable = excluded.is_deletable,
                tagged_os    = excluded.tagged_os,
                updated_at   = excluded.updated_at
            """,
            (
                file_id, job_id, file_path, name, ext, depth,
                chunk_count, engine,
                1 if is_deletable else 0,
                1 if tagged_os else 0,
                _now(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_indexed_files(
    job_id: str | None = None,
    limit: int = 500,
) -> list[dict]:
    """Return indexed_files rows, optionally filtered by job_id."""
    conn = _connect()
    try:
        if job_id:
            rows = conn.execute(
                "SELECT * FROM indexed_files WHERE job_id = ? "
                "ORDER BY updated_at DESC LIMIT ?",
                (job_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM indexed_files ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# Auto-create tables on import
ensure_table()
ensure_indexed_files_table()

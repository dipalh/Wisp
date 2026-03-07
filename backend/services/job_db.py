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
import time as _time
import json
from datetime import datetime, timezone
from hashlib import sha1
from pathlib import Path

from services.file_state import FileState

_DB_PATH = Path(__file__).resolve().parent.parent / "wisp_jobs.db"


def _db_path() -> str:
    """Return the database path as a string.  Indirection allows tests
    to monkey-patch ``_DB_PATH``."""
    return str(_DB_PATH)


_WRITE_MAX_RETRIES = 3
_WRITE_BASE_DELAY = 0.05  # 50 ms → 100 ms → 200 ms


def _connect() -> sqlite3.Connection:
    """Open a **new** connection with WAL mode and row_factory."""
    conn = sqlite3.connect(_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _with_write_retry(fn):
    """Execute *fn* with retries on ``OperationalError: database is locked``.

    Uses exponential backoff: 50 ms → 100 ms → 200 ms (3 retries max).
    """
    for attempt in range(_WRITE_MAX_RETRIES + 1):
        try:
            return fn()
        except sqlite3.OperationalError as exc:
            if "locked" in str(exc) and attempt < _WRITE_MAX_RETRIES:
                _time.sleep(_WRITE_BASE_DELAY * (2 ** attempt))
                continue
            raise


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
                stage            TEXT NOT NULL DEFAULT 'QUEUED',
                stats_json       TEXT NOT NULL DEFAULT '{}',
                progress_current INTEGER NOT NULL DEFAULT 0,
                progress_total   INTEGER NOT NULL DEFAULT 0,
                progress_message TEXT NOT NULL DEFAULT '',
                created_at       TEXT NOT NULL,
                updated_at       TEXT NOT NULL
            )
        """)
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
        }
        if "stage" not in existing:
            conn.execute(
                "ALTER TABLE jobs ADD COLUMN stage TEXT NOT NULL DEFAULT 'QUEUED'"
            )
        if "stats_json" not in existing:
            conn.execute(
                "ALTER TABLE jobs ADD COLUMN stats_json TEXT NOT NULL DEFAULT '{}'"
            )
        conn.commit()
    finally:
        conn.close()


# ── CRUD ──────────────────────────────────────────────────────────────


def create_job(job_id: str, job_type: str) -> None:
    """Insert a new job row with status='queued'."""
    def _do():
        now = _now()
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO jobs (job_id, type, status, progress_current, progress_total,
                                  progress_message, stage, stats_json, created_at, updated_at)
                VALUES (?, ?, 'queued', 0, 0, '', 'QUEUED', '{}', ?, ?)
                """,
                (job_id, job_type, now, now),
            )
            conn.commit()
        finally:
            conn.close()
    _with_write_retry(_do)


def get_job(job_id: str) -> dict | None:
    """Return full job row as a dict, or None if not found."""
    conn = _connect()
    try:
        row = conn.execute(
            "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()
        if row is None:
            return None
        data = dict(row)
        raw_stats = data.pop("stats_json", "{}") or "{}"
        try:
            data["stats"] = json.loads(raw_stats)
        except json.JSONDecodeError:
            data["stats"] = {}
        return data
    finally:
        conn.close()


def update_progress(
    job_id: str,
    current: int,
    total: int,
    message: str,
    stage: str | None = None,
    stats: dict | None = None,
) -> None:
    """Update progress fields + updated_at."""
    def _do():
        conn = _connect()
        try:
            if stage is not None or stats is not None:
                row = conn.execute(
                    "SELECT stage, stats_json FROM jobs WHERE job_id = ?",
                    (job_id,),
                ).fetchone()
                current_stage = row["stage"] if row is not None else "QUEUED"
                current_stats = row["stats_json"] if row is not None else "{}"
                conn.execute(
                    """
                    UPDATE jobs
                    SET progress_current = ?,
                        progress_total   = ?,
                        progress_message = ?,
                        stage            = ?,
                        stats_json       = ?,
                        updated_at       = ?
                    WHERE job_id = ?
                    """,
                    (
                        current,
                        total,
                        message,
                        stage or current_stage,
                        json.dumps(stats) if stats is not None else current_stats,
                        _now(),
                        job_id,
                    ),
                )
            else:
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
    _with_write_retry(_do)


def set_status(job_id: str, status: str, message: str = "") -> None:
    """Update status (and optionally progress_message) + updated_at."""
    def _do():
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
    _with_write_retry(_do)


def set_stage(job_id: str, stage: str) -> None:
    """Update the pipeline stage + updated_at."""
    def _do():
        conn = _connect()
        try:
            conn.execute(
                """
                UPDATE jobs
                SET stage = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (stage, _now(), job_id),
            )
            conn.commit()
        finally:
            conn.close()
    _with_write_retry(_do)


def set_stats(job_id: str, stats: dict[str, int]) -> None:
    """Persist scan/index summary counters for a job."""
    def _do():
        conn = _connect()
        try:
            conn.execute(
                """
                UPDATE jobs
                SET stats_json = ?, updated_at = ?
                WHERE job_id = ?
                """,
                (json.dumps(stats), _now(), job_id),
            )
            conn.commit()
        finally:
            conn.close()
    _with_write_retry(_do)


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
                file_state   TEXT NOT NULL DEFAULT 'INDEXED',
                fingerprint  TEXT NOT NULL DEFAULT '',
                last_seen_job_id TEXT NOT NULL DEFAULT '',
                error_code   TEXT NOT NULL DEFAULT '',
                error_message TEXT NOT NULL DEFAULT '',
                updated_at   TEXT NOT NULL
            )
        """)
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(indexed_files)").fetchall()
        }
        if "file_state" not in existing:
            conn.execute(
                "ALTER TABLE indexed_files "
                "ADD COLUMN file_state TEXT NOT NULL DEFAULT 'INDEXED'"
            )
        if "fingerprint" not in existing:
            conn.execute(
                "ALTER TABLE indexed_files "
                "ADD COLUMN fingerprint TEXT NOT NULL DEFAULT ''"
            )
        if "last_seen_job_id" not in existing:
            conn.execute(
                "ALTER TABLE indexed_files "
                "ADD COLUMN last_seen_job_id TEXT NOT NULL DEFAULT ''"
            )
        if "error_code" not in existing:
            conn.execute(
                "ALTER TABLE indexed_files "
                "ADD COLUMN error_code TEXT NOT NULL DEFAULT ''"
            )
        if "error_message" not in existing:
            conn.execute(
                "ALTER TABLE indexed_files "
                "ADD COLUMN error_message TEXT NOT NULL DEFAULT ''"
            )
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
    file_state: str = FileState.INDEXED.value,
    fingerprint: str | None = None,
    error_code: str = "",
    error_message: str = "",
) -> None:
    """Insert or update an indexed_files row."""
    def _do():
        computed_fingerprint = fingerprint
        if computed_fingerprint is None:
            computed_fingerprint = file_fingerprint(file_path)
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO indexed_files
                    (file_id, job_id, file_path, name, ext, depth,
                     chunk_count, engine, is_deletable, tagged_os,
                     file_state, fingerprint, last_seen_job_id,
                     error_code, error_message, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    file_state   = excluded.file_state,
                    fingerprint  = excluded.fingerprint,
                    last_seen_job_id = excluded.last_seen_job_id,
                    error_code   = excluded.error_code,
                    error_message = excluded.error_message,
                    updated_at   = excluded.updated_at
                """,
                (
                    file_id, job_id, file_path, name, ext, depth,
                    chunk_count, engine,
                    1 if is_deletable else 0,
                    1 if tagged_os else 0,
                    file_state,
                    computed_fingerprint,
                    job_id,
                    error_code,
                    error_message,
                    _now(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    _with_write_retry(_do)


def file_fingerprint(file_path: str) -> str:
    """Return a rename-stable filesystem fingerprint for reconciliation."""
    try:
        stat = Path(file_path).stat()
    except OSError:
        return ""
    raw = f"{stat.st_size}:{stat.st_mtime_ns}".encode("utf-8")
    return sha1(raw).hexdigest()


def _is_under_any_root(file_path: str, roots: list[str]) -> bool:
    if not roots:
        return True
    try:
        resolved = Path(file_path).resolve()
    except OSError:
        return False
    return any(resolved.is_relative_to(Path(root).resolve()) for root in roots)


def reconcile_indexed_files(job_id: str, root_paths: list[str]) -> None:
    """Reclassify previously indexed rows after a scan completes."""

    def _do():
        conn = _connect()
        try:
            rows = [
                dict(row)
                for row in conn.execute(
                    "SELECT file_id, file_path, fingerprint, last_seen_job_id, file_state "
                    "FROM indexed_files"
                ).fetchall()
            ]
            scoped_rows = [
                row for row in rows if _is_under_any_root(row["file_path"], root_paths)
            ]
            current_by_fingerprint = {
                row["fingerprint"]: row
                for row in scoped_rows
                if row["last_seen_job_id"] == job_id and row["fingerprint"]
            }

            for row in scoped_rows:
                if row["last_seen_job_id"] == job_id:
                    if row["file_state"] == FileState.PERMISSION_DENIED.value:
                        state = FileState.PERMISSION_DENIED.value
                    else:
                        state = FileState.INDEXED.value
                elif (
                    row["fingerprint"]
                    and row["fingerprint"] in current_by_fingerprint
                    and current_by_fingerprint[row["fingerprint"]]["file_path"] != row["file_path"]
                ):
                    state = FileState.MOVED_EXTERNALLY.value
                elif not Path(row["file_path"]).exists():
                    state = FileState.MISSING_EXTERNALLY.value
                else:
                    state = FileState.STALE.value

                conn.execute(
                    """
                    UPDATE indexed_files
                    SET file_state = ?, updated_at = ?
                    WHERE file_id = ?
                    """,
                    (state, _now(), row["file_id"]),
                )
            conn.commit()
        finally:
            conn.close()

    _with_write_retry(_do)


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

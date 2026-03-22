"""
SQLite-backed action store for durable action lifecycle state.

Public API (compatible with earlier in-memory version)
-----------------------------------------------------
  add(action)              -> Action
  get_all(status=None)     -> list[Action]
  get(id)                  -> Action | None
  set_status(id, status)   -> Action        (raises KeyError if not found)
  clear()                  -> None

Test/control helpers
--------------------
  configure_db(path)       -> None
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path

from services.actions.models import Action, ActionStatus

_lock = threading.Lock()
_DB_PATH = Path(__file__).resolve().parents[2] / "wisp_actions.db"


def configure_db(path: str | Path) -> None:
    """Point the store at a specific SQLite DB path (used by tests)."""
    global _DB_PATH
    _DB_PATH = Path(path)


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_DB_PATH), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _ensure_table() -> None:
    conn = _connect()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS actions (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                label TEXT NOT NULL,
                targets_json TEXT NOT NULL,
                before_state_json TEXT NOT NULL,
                after_state_json TEXT NOT NULL,
                timestamp REAL NOT NULL,
                status TEXT NOT NULL,
                proposal_id TEXT,
                batch_id TEXT,
                actor TEXT NOT NULL DEFAULT 'system',
                source TEXT,
                created_at REAL NOT NULL,
                applied_at REAL,
                failure_reason TEXT
            )
            """
        )
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(actions)").fetchall()
        }
        if "proposal_id" not in existing:
            conn.execute("ALTER TABLE actions ADD COLUMN proposal_id TEXT")
        if "batch_id" not in existing:
            conn.execute("ALTER TABLE actions ADD COLUMN batch_id TEXT")
        if "actor" not in existing:
            conn.execute("ALTER TABLE actions ADD COLUMN actor TEXT NOT NULL DEFAULT 'system'")
        if "source" not in existing:
            conn.execute("ALTER TABLE actions ADD COLUMN source TEXT")
        if "created_at" not in existing:
            conn.execute("ALTER TABLE actions ADD COLUMN created_at REAL NOT NULL DEFAULT 0")
        if "applied_at" not in existing:
            conn.execute("ALTER TABLE actions ADD COLUMN applied_at REAL")
        if "failure_reason" not in existing:
            conn.execute("ALTER TABLE actions ADD COLUMN failure_reason TEXT")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS action_batches (
                batch_id TEXT PRIMARY KEY,
                proposal_id TEXT,
                actor TEXT NOT NULL DEFAULT 'system',
                status TEXT NOT NULL,
                action_ids_json TEXT NOT NULL,
                created_at REAL NOT NULL,
                applied_at REAL,
                undone_at REAL,
                failure_reason TEXT
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _to_action(row: sqlite3.Row) -> Action:
    return Action(
        id=row["id"],
        type=row["type"],
        label=row["label"],
        targets=json.loads(row["targets_json"]),
        before_state=json.loads(row["before_state_json"]),
        after_state=json.loads(row["after_state_json"]),
        timestamp=row["timestamp"],
        proposal_id=row["proposal_id"],
        batch_id=row["batch_id"],
        actor=row["actor"] or "system",
        source=row["source"],
        created_at=row["created_at"] or row["timestamp"],
        applied_at=row["applied_at"],
        failure_reason=row["failure_reason"],
        status=ActionStatus(row["status"]),
    )


def add(action: Action) -> Action:
    """Persist and return an action."""
    with _lock:
        _ensure_table()
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT OR REPLACE INTO actions (
                    id, type, label, targets_json, before_state_json,
                    after_state_json, timestamp, status, proposal_id,
                    batch_id, actor, source, created_at, applied_at, failure_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action.id,
                    action.type.value,
                    action.label,
                    json.dumps(action.targets),
                    json.dumps(action.before_state),
                    json.dumps(action.after_state),
                    action.timestamp,
                    action.status.value,
                    action.proposal_id,
                    action.batch_id,
                    action.actor,
                    action.source,
                    action.created_at,
                    action.applied_at,
                    action.failure_reason,
                ),
            )
            conn.commit()
            return action
        finally:
            conn.close()


def get_all(status: ActionStatus | None = None) -> list[Action]:
    with _lock:
        _ensure_table()
        conn = _connect()
        try:
            if status is None:
                rows = conn.execute(
                    "SELECT * FROM actions ORDER BY timestamp ASC"
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM actions WHERE status = ? ORDER BY timestamp ASC",
                    (status.value,),
                ).fetchall()
            return [_to_action(row) for row in rows]
        finally:
            conn.close()


def get(action_id: str) -> Action | None:
    with _lock:
        _ensure_table()
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM actions WHERE id = ?",
                (action_id,),
            ).fetchone()
            if row is None:
                return None
            return _to_action(row)
        finally:
            conn.close()


def set_status(
    action_id: str,
    status: ActionStatus,
    *,
    failure_reason: str | None = None,
    applied_at: float | None = None,
) -> Action:
    with _lock:
        _ensure_table()
        conn = _connect()
        try:
            updated = conn.execute(
                "UPDATE actions SET status = ?, failure_reason = ?, applied_at = ? WHERE id = ?",
                (status.value, failure_reason, applied_at, action_id),
            )
            if updated.rowcount == 0:
                raise KeyError(f"Action '{action_id}' not found")
            conn.commit()
        finally:
            conn.close()
    action = get(action_id)
    if action is None:
        raise KeyError(f"Action '{action_id}' not found")
    return action


def clear() -> None:
    with _lock:
        _ensure_table()
        conn = _connect()
        try:
            conn.execute("DELETE FROM actions")
            conn.execute("DELETE FROM action_batches")
            conn.commit()
        finally:
            conn.close()


def create_batch(
    action_ids: list[str],
    *,
    proposal_id: str | None = None,
    actor: str = "system",
) -> dict:
    if not action_ids:
        raise ValueError("action_ids must not be empty")
    batch_id = f"batch_{uuid.uuid4().hex[:12]}"
    with _lock:
        _ensure_table()
        conn = _connect()
        try:
            conn.execute(
                """
                INSERT INTO action_batches (
                    batch_id, proposal_id, actor, status, action_ids_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    batch_id,
                    proposal_id,
                    actor,
                    ActionStatus.ACCEPTED.value,
                    json.dumps(action_ids),
                    time.time(),
                ),
            )
            conn.commit()
        finally:
            conn.close()
    return {
        "batch_id": batch_id,
        "proposal_id": proposal_id,
        "actor": actor,
        "status": ActionStatus.ACCEPTED.value,
        "action_ids": list(action_ids),
        "count": len(action_ids),
    }


def get_batch(batch_id: str) -> dict | None:
    with _lock:
        _ensure_table()
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT * FROM action_batches WHERE batch_id = ?",
                (batch_id,),
            ).fetchone()
            if row is None:
                return None
            return {
                "batch_id": row["batch_id"],
                "proposal_id": row["proposal_id"],
                "actor": row["actor"],
                "status": row["status"],
                "action_ids": json.loads(row["action_ids_json"]),
                "created_at": row["created_at"],
                "applied_at": row["applied_at"],
                "undone_at": row["undone_at"],
                "failure_reason": row["failure_reason"],
            }
        finally:
            conn.close()


def set_batch_status(
    batch_id: str,
    status: ActionStatus,
    *,
    failure_reason: str | None = None,
) -> dict:
    with _lock:
        _ensure_table()
        conn = _connect()
        try:
            updated = conn.execute(
                """
                UPDATE action_batches
                SET status = ?, applied_at = ?, undone_at = ?, failure_reason = ?
                WHERE batch_id = ?
                """,
                (
                    status.value,
                    time.time() if status in (ActionStatus.APPLIED, ActionStatus.PARTIAL, ActionStatus.FAILED) else None,
                    time.time() if status == ActionStatus.UNDONE else None,
                    failure_reason,
                    batch_id,
                ),
            )
            if updated.rowcount == 0:
                raise KeyError(f"Batch '{batch_id}' not found")
            conn.commit()
        finally:
            conn.close()
    batch = get_batch(batch_id)
    if batch is None:
        raise KeyError(f"Batch '{batch_id}' not found")
    return batch

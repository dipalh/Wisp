"""
Tests for SQLite robustness in services/job_db.py.

Verifies:
  1. Connection timeout is at least 30 seconds (not 5).
  2. Writes survive a brief "database is locked" error via retry.
  3. Rapid sequential writes don't error under WAL mode.
"""
from __future__ import annotations

import sqlite3
from unittest.mock import patch

import pytest

import services.job_db as job_db


@pytest.fixture(autouse=True)
def _use_temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_jobs.db"
    monkeypatch.setattr(job_db, "_DB_PATH", db_file)
    job_db.ensure_table()
    job_db.ensure_indexed_files_table()
    yield


# ═══════════════════════════════════════════════════════════════════════
#  Timeout
# ═══════════════════════════════════════════════════════════════════════


def test_connection_timeout_at_least_30s():
    """The SQLite connection timeout must be >= 30s to handle lock contention."""
    captured = {}
    original_connect = sqlite3.connect

    def _spy_connect(*args, **kwargs):
        captured.update(kwargs)
        if len(args) >= 2:
            captured["timeout_positional"] = args[1]
        return original_connect(*args, **kwargs)

    with patch("services.job_db.sqlite3.connect", side_effect=_spy_connect):
        conn = job_db._connect()
        conn.close()

    timeout = captured.get("timeout", captured.get("timeout_positional", 5))
    assert timeout >= 30, f"Expected timeout >= 30, got {timeout}"


# ═══════════════════════════════════════════════════════════════════════
#  Retry on "database is locked"
# ═══════════════════════════════════════════════════════════════════════


def test_update_progress_retries_on_locked():
    """A brief 'database is locked' error should be retried, not fatal."""
    job_db.create_job("retry1", "scan")

    call_count = {"n": 0}
    real_connect = job_db._connect

    def _flaky_connect():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return real_connect()

    with patch.object(job_db, "_connect", side_effect=_flaky_connect):
        job_db.update_progress("retry1", 10, 50, "retried ok")

    job = job_db.get_job("retry1")
    assert job["progress_current"] == 10
    assert job["progress_message"] == "retried ok"


def test_set_status_retries_on_locked():
    """set_status should also retry on locked."""
    job_db.create_job("retry2", "scan")

    call_count = {"n": 0}
    real_connect = job_db._connect

    def _flaky_connect():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return real_connect()

    with patch.object(job_db, "_connect", side_effect=_flaky_connect):
        job_db.set_status("retry2", "running")

    assert job_db.get_job("retry2")["status"] == "running"


def test_upsert_indexed_file_retries_on_locked():
    """upsert_indexed_file should also retry on locked."""
    call_count = {"n": 0}
    real_connect = job_db._connect

    def _flaky_connect():
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return real_connect()

    with patch.object(job_db, "_connect", side_effect=_flaky_connect):
        job_db.upsert_indexed_file(
            file_id="fR", job_id="jR", file_path="/a.txt", name="a.txt",
            ext=".txt", depth="deep", chunk_count=3, engine="local",
            is_deletable=False, tagged_os=False,
        )

    rows = job_db.get_indexed_files()
    assert len(rows) == 1
    assert rows[0]["file_id"] == "fR"


def test_gives_up_after_max_retries():
    """After exhausting retries, the error should propagate."""
    job_db.create_job("giveup1", "scan")

    def _always_locked():
        raise sqlite3.OperationalError("database is locked")

    with patch.object(job_db, "_connect", side_effect=_always_locked):
        with pytest.raises(sqlite3.OperationalError, match="locked"):
            job_db.update_progress("giveup1", 1, 10, "nope")


# ═══════════════════════════════════════════════════════════════════════
#  Rapid writes don't error
# ═══════════════════════════════════════════════════════════════════════


def test_rapid_progress_updates_succeed():
    """100 rapid sequential progress updates must not raise."""
    job_db.create_job("rapid1", "scan")

    for i in range(100):
        job_db.update_progress("rapid1", i + 1, 100, f"File {i + 1}")

    job = job_db.get_job("rapid1")
    assert job["progress_current"] == 100
    assert job["progress_total"] == 100


def test_rapid_upsert_indexed_files():
    """50 rapid upserts to indexed_files must not raise."""
    for i in range(50):
        job_db.upsert_indexed_file(
            file_id=f"f{i}",
            job_id="rapid_j",
            file_path=f"/tmp/file{i}.txt",
            name=f"file{i}.txt",
            ext=".txt",
            depth="deep",
            chunk_count=3,
            engine="local",
            is_deletable=False,
            tagged_os=False,
        )

    rows = job_db.get_indexed_files(job_id="rapid_j")
    assert len(rows) == 50

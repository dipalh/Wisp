"""
Unit tests for services/job_db.py

Covers:
  - create_job inserts and get_job returns expected fields
  - update_progress updates progress_current/total/message + updated_at
  - set_status updates status and updated_at
  - set_status with message updates progress_message
  - unknown job_id returns None
"""
import os
import time
import pytest
import services.job_db as job_db


@pytest.fixture(autouse=True)
def _use_temp_db(tmp_path, monkeypatch):
    """Point job_db at a fresh temp database for every test."""
    db_file = tmp_path / "test_jobs.db"
    monkeypatch.setattr(job_db, "_DB_PATH", db_file)
    job_db.ensure_table()
    yield


# ── create_job + get_job ────────────────────────────────────────────────


def test_create_and_get():
    job_db.create_job("abc123", "scan")
    job = job_db.get_job("abc123")

    assert job is not None
    assert job["job_id"] == "abc123"
    assert job["type"] == "scan"
    assert job["status"] == "queued"
    assert job["progress_current"] == 0
    assert job["progress_total"] == 0
    assert job["progress_message"] == ""
    assert job["created_at"] != ""
    assert job["updated_at"] != ""


def test_get_unknown_returns_none():
    result = job_db.get_job("nonexistent")
    assert result is None


# ── update_progress ─────────────────────────────────────────────────────


def test_update_progress():
    job_db.create_job("prog1", "scan")
    before = job_db.get_job("prog1")

    time.sleep(0.01)  # ensure updated_at changes
    job_db.update_progress("prog1", 25, 50, "Processing file 25")

    after = job_db.get_job("prog1")
    assert after["progress_current"] == 25
    assert after["progress_total"] == 50
    assert after["progress_message"] == "Processing file 25"
    assert after["updated_at"] > before["updated_at"]
    # status should NOT change
    assert after["status"] == "queued"


# ── set_status ──────────────────────────────────────────────────────────


def test_set_status_without_message():
    job_db.create_job("stat1", "scan")
    before = job_db.get_job("stat1")

    time.sleep(0.01)
    job_db.set_status("stat1", "running")

    after = job_db.get_job("stat1")
    assert after["status"] == "running"
    assert after["updated_at"] > before["updated_at"]
    # progress_message should stay empty
    assert after["progress_message"] == ""


def test_set_status_with_message():
    job_db.create_job("stat2", "scan")
    job_db.set_status("stat2", "failed", "something broke")

    job = job_db.get_job("stat2")
    assert job["status"] == "failed"
    assert job["progress_message"] == "something broke"


# ── Full lifecycle ──────────────────────────────────────────────────────


def test_full_lifecycle():
    """queued -> running -> progress updates -> success"""
    job_db.create_job("life1", "scan")
    assert job_db.get_job("life1")["status"] == "queued"

    job_db.set_status("life1", "running")
    assert job_db.get_job("life1")["status"] == "running"

    job_db.update_progress("life1", 10, 50, "File 10")
    job = job_db.get_job("life1")
    assert job["progress_current"] == 10
    assert job["progress_total"] == 50

    job_db.update_progress("life1", 50, 50, "File 50")
    job_db.set_status("life1", "success", "Done")

    final = job_db.get_job("life1")
    assert final["status"] == "success"
    assert final["progress_current"] == 50
    assert final["progress_message"] == "Done"

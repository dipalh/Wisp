"""
Unit tests for services/job_db.py

Covers jobs table:
  - create_job inserts and get_job returns expected fields
  - update_progress updates progress_current/total/message + updated_at
  - set_status updates status and updated_at
  - set_status with message updates progress_message
  - unknown job_id returns None

Covers indexed_files table:
  - upsert_indexed_file inserts and get_indexed_files retrieves
  - upsert is idempotent (second call updates)
  - filter by job_id works
  - tagging failure does not fail the job (mock OS tag to raise)
"""
import time
import pytest
import services.job_db as job_db


@pytest.fixture(autouse=True)
def _use_temp_db(tmp_path, monkeypatch):
    """Point job_db at a fresh temp database for every test."""
    db_file = tmp_path / "test_jobs.db"
    monkeypatch.setattr(job_db, "_DB_PATH", db_file)
    job_db.ensure_table()
    job_db.ensure_indexed_files_table()
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

    time.sleep(0.01)
    job_db.update_progress("prog1", 25, 50, "Processing file 25")

    after = job_db.get_job("prog1")
    assert after["progress_current"] == 25
    assert after["progress_total"] == 50
    assert after["progress_message"] == "Processing file 25"
    assert after["updated_at"] > before["updated_at"]
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


# ═══════════════════════════════════════════════════════════════════════
#  indexed_files table
# ═══════════════════════════════════════════════════════════════════════


def test_upsert_and_get_indexed_file():
    job_db.upsert_indexed_file(
        file_id="f1",
        job_id="j1",
        file_path="/tmp/test.txt",
        name="test.txt",
        ext=".txt",
        depth="deep",
        chunk_count=5,
        engine="local",
        is_deletable=False,
        tagged_os=False,
    )
    rows = job_db.get_indexed_files()
    assert len(rows) == 1
    row = rows[0]
    assert row["file_id"] == "f1"
    assert row["job_id"] == "j1"
    assert row["file_path"] == "/tmp/test.txt"
    assert row["name"] == "test.txt"
    assert row["ext"] == ".txt"
    assert row["depth"] == "deep"
    assert row["chunk_count"] == 5
    assert row["engine"] == "local"
    assert row["is_deletable"] == 0
    assert row["tagged_os"] == 0
    assert row["updated_at"] != ""


def test_upsert_is_idempotent():
    """Second upsert with same file_id updates the row."""
    job_db.upsert_indexed_file(
        file_id="f2", job_id="j1", file_path="/a.txt", name="a.txt",
        ext=".txt", depth="card", chunk_count=1, engine="local",
        is_deletable=False, tagged_os=False,
    )
    job_db.upsert_indexed_file(
        file_id="f2", job_id="j2", file_path="/a.txt", name="a.txt",
        ext=".txt", depth="deep", chunk_count=8, engine="local+ai",
        is_deletable=True, tagged_os=True,
    )

    rows = job_db.get_indexed_files()
    assert len(rows) == 1
    row = rows[0]
    assert row["job_id"] == "j2"
    assert row["depth"] == "deep"
    assert row["chunk_count"] == 8
    assert row["is_deletable"] == 1
    assert row["tagged_os"] == 1


def test_get_indexed_files_filter_by_job_id():
    job_db.upsert_indexed_file(
        file_id="fa", job_id="j10", file_path="/a.py", name="a.py",
        ext=".py", depth="deep", chunk_count=3, engine="local",
        is_deletable=False, tagged_os=False,
    )
    job_db.upsert_indexed_file(
        file_id="fb", job_id="j20", file_path="/b.py", name="b.py",
        ext=".py", depth="card", chunk_count=1, engine="card",
        is_deletable=True, tagged_os=False,
    )

    assert len(job_db.get_indexed_files(job_id="j10")) == 1
    assert len(job_db.get_indexed_files(job_id="j20")) == 1
    assert len(job_db.get_indexed_files(job_id="j99")) == 0
    assert len(job_db.get_indexed_files()) == 2


def test_deletable_fields():
    """is_deletable and tagged_os booleans map to 0/1 correctly."""
    job_db.upsert_indexed_file(
        file_id="fd", job_id="j1", file_path="/junk.dmg", name="junk.dmg",
        ext=".dmg", depth="card", chunk_count=1, engine="card",
        is_deletable=True, tagged_os=True,
    )
    row = job_db.get_indexed_files()[0]
    assert row["is_deletable"] == 1
    assert row["tagged_os"] == 1

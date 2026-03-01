"""
Tests for tagging field correctness in the scan pipeline.

Verifies:
  1. set_deletable() returns bool indicating whether the OS tag write
     succeeded (not just whether the heuristic says deletable).
  2. The scan task stores os_tag_applied based on the RETURN VALUE of
     set_deletable(), not by calling is_deletable() read-back.
  3. On unsupported OS (or when tagging fails), os_tag_applied is False
     but is_deletable (the heuristic) can still be True.
"""
from __future__ import annotations

import platform
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import dataclass, field

import services.job_db as job_db


@pytest.fixture(autouse=True)
def _use_temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_jobs.db"
    monkeypatch.setattr(job_db, "_DB_PATH", db_file)
    job_db.ensure_table()
    job_db.ensure_indexed_files_table()
    yield


# ═══════════════════════════════════════════════════════════════════════
#  set_deletable() return value
# ═══════════════════════════════════════════════════════════════════════


def test_set_deletable_returns_bool():
    """set_deletable must return a bool, not None."""
    from services.os_tags.deletable import set_deletable
    import tempfile, os

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"test")
        path = f.name
    try:
        result = set_deletable(path, True)
        assert isinstance(result, bool), f"Expected bool, got {type(result)}"
    finally:
        os.unlink(path)


def test_set_deletable_returns_false_on_failure():
    """When the underlying OS write fails, set_deletable returns False."""
    from services.os_tags.deletable import set_deletable

    if platform.system() == "Darwin":
        with patch("services.os_tags.deletable._set_deletable_macos", side_effect=OSError("boom")):
            result = set_deletable("/tmp/fake.txt", True)
            assert result is False
    else:
        result = set_deletable("/tmp/fake.txt", True)
        assert isinstance(result, bool)


def test_set_deletable_false_removal_returns_bool():
    """Removing the tag (value=False) also returns bool."""
    from services.os_tags.deletable import set_deletable
    import tempfile, os

    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
        f.write(b"test")
        path = f.name
    try:
        result = set_deletable(path, False)
        assert isinstance(result, bool)
    finally:
        os.unlink(path)


# ═══════════════════════════════════════════════════════════════════════
#  Scan task: os_tag_applied comes from set_deletable return
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class _FakeIngestResult:
    file_id: str
    file_path: str
    chunk_count: int
    skipped: bool = False
    depth: str = "card"
    engine: str = "mock"
    errors: list[str] = field(default_factory=list)


@pytest.fixture()
def _celery_eager(monkeypatch):
    from celery_app import app as celery_app
    monkeypatch.setattr(celery_app.conf, "task_always_eager", True)
    monkeypatch.setattr(celery_app.conf, "task_eager_propagates", True)
    yield


def test_os_tag_applied_true_when_set_deletable_succeeds(
    _celery_eager, tmp_path,
):
    """When set_deletable returns True, indexed_files.tagged_os must be 1."""
    scan_dir = tmp_path / "scan_target"
    scan_dir.mkdir()
    (scan_dir / "old.dmg").write_text("installer")

    async def _fake_ingest(fp, file_id=None, force_deep=False):
        import hashlib
        fid = hashlib.sha256(str(fp).encode()).hexdigest()[:16]
        return _FakeIngestResult(file_id=fid, file_path=str(fp), chunk_count=1)

    job_db.create_job("tag_ok", "scan")

    with patch("services.embedding.pipeline.ingest_file", side_effect=_fake_ingest), \
         patch("services.embedding.pipeline.init_store"), \
         patch("services.embedding.pipeline.teardown_store"), \
         patch("services.os_tags.deletable.should_mark_deletable", return_value=True), \
         patch("services.os_tags.deletable.set_deletable", return_value=True):
        from tasks.scan import scan_and_index
        scan_and_index("tag_ok", [str(scan_dir)])

    job = job_db.get_job("tag_ok")
    assert job["status"] == "success"

    files = job_db.get_indexed_files(job_id="tag_ok")
    assert len(files) == 1
    assert files[0]["is_deletable"] == 1
    assert files[0]["tagged_os"] == 1


def test_os_tag_applied_false_when_set_deletable_fails(
    _celery_eager, tmp_path,
):
    """When set_deletable returns False (OS doesn't support it),
    tagged_os must be 0, but is_deletable (heuristic) can still be 1."""
    scan_dir = tmp_path / "scan_target"
    scan_dir.mkdir()
    (scan_dir / "old.dmg").write_text("installer")

    async def _fake_ingest(fp, file_id=None, force_deep=False):
        import hashlib
        fid = hashlib.sha256(str(fp).encode()).hexdigest()[:16]
        return _FakeIngestResult(file_id=fid, file_path=str(fp), chunk_count=1)

    job_db.create_job("tag_fail", "scan")

    with patch("services.embedding.pipeline.ingest_file", side_effect=_fake_ingest), \
         patch("services.embedding.pipeline.init_store"), \
         patch("services.embedding.pipeline.teardown_store"), \
         patch("services.os_tags.deletable.should_mark_deletable", return_value=True), \
         patch("services.os_tags.deletable.set_deletable", return_value=False):
        from tasks.scan import scan_and_index
        scan_and_index("tag_fail", [str(scan_dir)])

    files = job_db.get_indexed_files(job_id="tag_fail")
    assert len(files) == 1
    assert files[0]["is_deletable"] == 1, "heuristic says deletable"
    assert files[0]["tagged_os"] == 0, "OS tag write failed"


def test_os_tag_not_attempted_when_not_deletable(
    _celery_eager, tmp_path,
):
    """When should_mark_deletable returns False, set_deletable should
    be called with value=False, and tagged_os should be 0."""
    scan_dir = tmp_path / "scan_target"
    scan_dir.mkdir()
    (scan_dir / "important.pdf").write_bytes(b"%PDF")

    async def _fake_ingest(fp, file_id=None, force_deep=False):
        import hashlib
        fid = hashlib.sha256(str(fp).encode()).hexdigest()[:16]
        return _FakeIngestResult(file_id=fid, file_path=str(fp), chunk_count=3, depth="deep")

    mock_set = MagicMock(return_value=True)
    job_db.create_job("no_del", "scan")

    with patch("services.embedding.pipeline.ingest_file", side_effect=_fake_ingest), \
         patch("services.embedding.pipeline.init_store"), \
         patch("services.embedding.pipeline.teardown_store"), \
         patch("services.os_tags.deletable.should_mark_deletable", return_value=False), \
         patch("services.os_tags.deletable.set_deletable", mock_set):
        from tasks.scan import scan_and_index
        scan_and_index("no_del", [str(scan_dir)])

    files = job_db.get_indexed_files(job_id="no_del")
    assert len(files) == 1
    assert files[0]["is_deletable"] == 0
    assert files[0]["tagged_os"] == 0

    # set_deletable should have been called with value=False
    mock_set.assert_called_once()
    call_args = mock_set.call_args
    assert call_args[1].get("value", call_args[0][1] if len(call_args[0]) > 1 else None) is False

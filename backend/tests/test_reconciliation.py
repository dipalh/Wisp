from __future__ import annotations

import hashlib
import errno
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.job_db as job_db


@pytest.fixture(autouse=True)
def _use_temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "test_jobs.db"
    monkeypatch.setattr(job_db, "_DB_PATH", db_file)
    job_db.ensure_table()
    job_db.ensure_indexed_files_table()
    yield


@pytest.fixture()
def _celery_eager(monkeypatch):
    from celery_app import app as celery_app

    monkeypatch.setattr(celery_app.conf, "task_always_eager", True)
    monkeypatch.setattr(celery_app.conf, "task_eager_propagates", True)
    yield


@pytest.fixture()
def client():
    from api.v1.jobs import router as jobs_router

    test_app = FastAPI()
    test_app.include_router(jobs_router, prefix="/api/v1/jobs")
    return TestClient(test_app)


@dataclass
class _FakeIngestResult:
    file_id: str
    file_path: str
    chunk_count: int
    skipped: bool = False
    depth: str = "deep"
    engine: str = "mock"
    errors: list[str] = field(default_factory=list)


async def _fake_ingest(file_path: Path, file_id=None, force_deep=False):
    fid = hashlib.sha256(str(file_path).encode()).hexdigest()[:16]
    return _FakeIngestResult(
        file_id=fid,
        file_path=str(file_path),
        chunk_count=1,
    )


def _run_scan(client: TestClient, folder: Path):
    with patch("services.embedding.pipeline.ingest_file", side_effect=_fake_ingest), \
         patch("services.embedding.pipeline.init_store"), \
         patch("services.embedding.pipeline.teardown_store"):
        resp = client.post("/api/v1/jobs/scan", json={"folders": [str(folder)]})
    assert resp.status_code == 200
    return resp.json()["job_id"]


def test_rescan_marks_deleted_file_missing_externally(client, _celery_eager, tmp_path):
    scan_dir = tmp_path / "scan_target"
    scan_dir.mkdir()
    victim = scan_dir / "hello.txt"
    victim.write_text("hello world")

    first_job_id = _run_scan(client, scan_dir)
    first_rows = job_db.get_indexed_files(job_id=first_job_id)
    assert len(first_rows) == 1
    assert first_rows[0]["file_state"] == "INDEXED"

    victim.unlink()

    second_job_id = _run_scan(client, scan_dir)
    second_rows = job_db.get_indexed_files()
    stale_row = next(row for row in second_rows if row["job_id"] == first_job_id)

    assert second_job_id != first_job_id
    assert stale_row["file_state"] == "MISSING_EXTERNALLY"


def test_rescan_marks_renamed_file_moved_externally_and_adds_new_row(client, _celery_eager, tmp_path):
    scan_dir = tmp_path / "scan_target"
    scan_dir.mkdir()
    original = scan_dir / "hello.txt"
    original.write_text("hello world")

    first_job_id = _run_scan(client, scan_dir)

    renamed = scan_dir / "renamed.txt"
    original.rename(renamed)

    second_job_id = _run_scan(client, scan_dir)
    rows = job_db.get_indexed_files()

    old_row = next(row for row in rows if row["job_id"] == first_job_id)
    new_row = next(row for row in rows if row["job_id"] == second_job_id)

    assert old_row["file_path"].endswith("hello.txt")
    assert old_row["file_state"] == "MOVED_EXTERNALLY"
    assert new_row["file_path"].endswith("renamed.txt")
    assert new_row["file_state"] == "INDEXED"


def test_indexed_files_endpoint_exposes_file_state(client, _celery_eager, tmp_path):
    scan_dir = tmp_path / "scan_target"
    scan_dir.mkdir()
    victim = scan_dir / "hello.txt"
    victim.write_text("hello world")

    _run_scan(client, scan_dir)
    victim.unlink()
    _run_scan(client, scan_dir)

    resp = client.get("/api/v1/jobs/indexed-files")
    assert resp.status_code == 200

    files = resp.json()["files"]
    assert any(row["file_state"] == "MISSING_EXTERNALLY" for row in files)


def test_permission_denied_during_scan_is_recorded_as_recoverable_state(
    client,
    _celery_eager,
    tmp_path,
):
    scan_dir = tmp_path / "scan_target"
    scan_dir.mkdir()
    visible = scan_dir / "visible.txt"
    visible.write_text("hello world")
    protected = scan_dir / "secret"
    protected.mkdir()

    from services.ingestor import scanner as scanner_module

    original_iterdir = scanner_module.Path.iterdir

    def _iterdir_with_permission_denied(path_obj):
        if path_obj == protected:
            raise PermissionError("permission denied")
        return original_iterdir(path_obj)

    with patch.object(scanner_module.Path, "iterdir", autospec=True, side_effect=_iterdir_with_permission_denied):
        job_id = _run_scan(client, scan_dir)

    rows = job_db.get_indexed_files(job_id=job_id)
    indexed_row = next(row for row in rows if row["file_path"].endswith("visible.txt"))
    denied_row = next(row for row in rows if row["file_path"].endswith("secret"))

    assert indexed_row["file_state"] == "INDEXED"
    assert denied_row["file_state"] == "PERMISSION_DENIED"
    assert denied_row["error_code"] == "PERMISSION_DENIED"
    assert "permission denied" in denied_row["error_message"].lower()


def test_locked_directory_during_scan_is_recorded_as_locked_state(
    client,
    _celery_eager,
    tmp_path,
):
    scan_dir = tmp_path / "scan_target"
    scan_dir.mkdir()
    visible = scan_dir / "visible.txt"
    visible.write_text("hello world")
    locked = scan_dir / "locked"
    locked.mkdir()

    from services.ingestor import scanner as scanner_module

    original_iterdir = scanner_module.Path.iterdir

    def _iterdir_with_locked(path_obj):
        if path_obj == locked:
            raise OSError(errno.EBUSY, "Resource busy: file is locked")
        return original_iterdir(path_obj)

    with patch.object(scanner_module.Path, "iterdir", autospec=True, side_effect=_iterdir_with_locked):
        job_id = _run_scan(client, scan_dir)

    rows = job_db.get_indexed_files(job_id=job_id)
    indexed_row = next(row for row in rows if row["file_path"].endswith("visible.txt"))
    locked_row = next(row for row in rows if row["file_path"].endswith("locked"))

    assert indexed_row["file_state"] == "INDEXED"
    assert locked_row["file_state"] == "LOCKED"
    assert locked_row["error_code"] == "LOCKED"
    assert "locked" in locked_row["error_message"].lower()

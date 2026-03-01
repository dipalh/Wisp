"""
FastAPI TestClient tests for api/v1/jobs.py

Uses an isolated FastAPI app that only mounts the jobs router,
avoiding the elevenlabs / other optional import chain from main.py.

Celery is configured in eager mode so tasks run synchronously
without needing Redis or a Celery worker.

Covers:
  - POST /api/v1/jobs/scan requires folders body
  - POST /api/v1/jobs/scan returns job_id
  - GET  /api/v1/jobs/{job_id} returns queued state
  - GET  unknown job_id returns 404
  - GET  /api/v1/jobs/indexed-files returns files
  - With eager mode + mocked pipeline: scan indexes temp files end-to-end
  - Tagging failure does not crash the task
"""
import pytest
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.job_db as job_db


@pytest.fixture(autouse=True)
def _use_temp_db(tmp_path, monkeypatch):
    """Point job_db at a fresh temp database for every test."""
    db_file = tmp_path / "test_jobs.db"
    monkeypatch.setattr(job_db, "_DB_PATH", db_file)
    job_db.ensure_table()
    job_db.ensure_indexed_files_table()
    yield


@pytest.fixture()
def _celery_eager(monkeypatch):
    """Configure Celery to execute tasks synchronously (eager mode)."""
    from celery_app import app as celery_app
    monkeypatch.setattr(celery_app.conf, "task_always_eager", True)
    monkeypatch.setattr(celery_app.conf, "task_eager_propagates", True)
    yield


@pytest.fixture()
def client():
    """TestClient against a minimal app with only the jobs router."""
    from api.v1.jobs import router as jobs_router

    test_app = FastAPI()
    test_app.include_router(jobs_router, prefix="/api/v1/jobs")
    return TestClient(test_app)


# ── POST /api/v1/jobs/scan ──────────────────────────────────────────────


def test_post_scan_returns_job_id(client):
    resp = client.post("/api/v1/jobs/scan", json={"folders": ["/tmp"]})
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert len(data["job_id"]) == 32


def test_post_scan_requires_folders(client):
    resp = client.post("/api/v1/jobs/scan", json={"folders": []})
    assert resp.status_code == 400


def test_post_scan_rejects_missing_body(client):
    resp = client.post("/api/v1/jobs/scan")
    assert resp.status_code == 422


# ── GET /api/v1/jobs/{job_id} ───────────────────────────────────────────


def test_get_job_returns_queued(client):
    post_resp = client.post("/api/v1/jobs/scan", json={"folders": ["/tmp"]})
    job_id = post_resp.json()["job_id"]

    job = job_db.get_job(job_id)
    assert job is not None
    assert job["status"] == "queued"

    get_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["job_id"] == job_id
    assert data["type"] == "scan"
    assert data["status"] == "queued"


def test_get_unknown_job_returns_404(client):
    resp = client.get("/api/v1/jobs/doesnotexist")
    assert resp.status_code == 404


# ── GET /api/v1/jobs/indexed-files ──────────────────────────────────────


def test_indexed_files_endpoint_empty(client):
    resp = client.get("/api/v1/jobs/indexed-files")
    assert resp.status_code == 200
    data = resp.json()
    assert data["files"] == []
    assert data["total"] == 0


def test_indexed_files_returns_data(client):
    job_db.upsert_indexed_file(
        file_id="f1", job_id="j1", file_path="/a.txt", name="a.txt",
        ext=".txt", depth="deep", chunk_count=3, engine="local",
        is_deletable=False, tagged_os=False,
    )
    resp = client.get("/api/v1/jobs/indexed-files")
    data = resp.json()
    assert data["total"] == 1
    assert data["files"][0]["file_id"] == "f1"


def test_indexed_files_filter_by_job_id(client):
    job_db.upsert_indexed_file(
        file_id="f1", job_id="j1", file_path="/a.txt", name="a.txt",
        ext=".txt", depth="deep", chunk_count=3, engine="local",
        is_deletable=False, tagged_os=False,
    )
    job_db.upsert_indexed_file(
        file_id="f2", job_id="j2", file_path="/b.txt", name="b.txt",
        ext=".txt", depth="card", chunk_count=1, engine="card",
        is_deletable=False, tagged_os=False,
    )
    resp = client.get("/api/v1/jobs/indexed-files?job_id=j1")
    assert resp.json()["total"] == 1


# ── Eager-mode end-to-end (mocked pipeline) ─────────────────────────────


@dataclass
class _FakeIngestResult:
    file_id: str
    file_path: str
    chunk_count: int
    skipped: bool = False
    depth: str = "deep"
    engine: str = "mock"
    errors: list[str] = field(default_factory=list)


def test_eager_scan_with_mocked_pipeline(client, _celery_eager, tmp_path):
    """Eager mode: scan_and_index runs the pipeline (mocked) end-to-end."""
    scan_dir = tmp_path / "scan_target"
    scan_dir.mkdir()
    for name in ["a.txt", "b.py", "c.md"]:
        (scan_dir / name).write_text(f"content of {name}")

    async def _fake_ingest(file_path, file_id=None, force_deep=False):
        import hashlib
        fid = hashlib.sha256(str(file_path).encode()).hexdigest()[:16]
        return _FakeIngestResult(
            file_id=fid,
            file_path=str(file_path),
            chunk_count=3,
        )

    with patch("services.embedding.pipeline.ingest_file", side_effect=_fake_ingest), \
         patch("services.embedding.pipeline.init_store"), \
         patch("services.embedding.pipeline.teardown_store"):
        resp = client.post(
            "/api/v1/jobs/scan",
            json={"folders": [str(scan_dir)]},
        )

    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    job = job_db.get_job(job_id)
    assert job["status"] == "success"
    assert job["progress_current"] == 3
    assert job["progress_total"] == 3

    files_resp = client.get(f"/api/v1/jobs/indexed-files?job_id={job_id}")
    assert files_resp.json()["total"] == 3


def test_tagging_failure_does_not_crash_task(client, _celery_eager, tmp_path):
    """OS tagging failure must not fail the scan job."""
    scan_dir = tmp_path / "scan_target"
    scan_dir.mkdir()
    (scan_dir / "old.dmg").write_text("installer")

    async def _fake_ingest(file_path, file_id=None, force_deep=False):
        import hashlib
        fid = hashlib.sha256(str(file_path).encode()).hexdigest()[:16]
        return _FakeIngestResult(
            file_id=fid, file_path=str(file_path), chunk_count=1, depth="card",
        )

    def _raise(*a, **kw):
        raise OSError("xattr not supported")

    with patch("services.embedding.pipeline.ingest_file", side_effect=_fake_ingest), \
         patch("services.embedding.pipeline.init_store"), \
         patch("services.embedding.pipeline.teardown_store"), \
         patch("services.os_tags.deletable.should_mark_deletable", side_effect=_raise), \
         patch("services.os_tags.deletable.is_deletable", side_effect=_raise):
            resp = client.post(
                "/api/v1/jobs/scan",
                json={"folders": [str(scan_dir)]},
            )

    job_id = resp.json()["job_id"]
    job = job_db.get_job(job_id)
    assert job["status"] == "success"

    files = job_db.get_indexed_files(job_id=job_id)
    assert len(files) == 1
    assert files[0]["is_deletable"] == 0

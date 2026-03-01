"""
FastAPI TestClient tests for api/v1/jobs.py

Uses an isolated FastAPI app that only mounts the jobs router,
avoiding the elevenlabs / other optional import chain from main.py.

Celery is configured in eager mode so tasks run synchronously
without needing Redis or a Celery worker.

Covers:
  - POST /api/v1/jobs/scan returns job_id
  - GET  /api/v1/jobs/{job_id} returns queued state initially
  - GET  unknown job_id returns 404
  - With eager mode: POST triggers task, job finishes success with 50/50
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.job_db as job_db


@pytest.fixture(autouse=True)
def _use_temp_db(tmp_path, monkeypatch):
    """Point job_db at a fresh temp database for every test."""
    db_file = tmp_path / "test_jobs.db"
    monkeypatch.setattr(job_db, "_DB_PATH", db_file)
    job_db.ensure_table()
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
    resp = client.post("/api/v1/jobs/scan")
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert len(data["job_id"]) == 32  # uuid hex


# ── GET /api/v1/jobs/{job_id} ───────────────────────────────────────────


def test_get_job_returns_queued(client):
    """POST creates a row, GET returns it in queued status.

    Without eager mode the Celery task is not executed, so status
    stays 'queued'.
    """
    post_resp = client.post("/api/v1/jobs/scan")
    job_id = post_resp.json()["job_id"]

    # Without eager mode, task dispatch is a no-op (no worker),
    # but the row should still exist in queued state.
    # We directly read the db to confirm:
    job = job_db.get_job(job_id)
    assert job is not None
    assert job["status"] == "queued"

    get_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert get_resp.status_code == 200
    data = get_resp.json()
    assert data["job_id"] == job_id
    assert data["type"] == "scan"
    assert data["status"] == "queued"
    assert data["progress_current"] == 0
    assert data["progress_total"] == 0


def test_get_unknown_job_returns_404(client):
    resp = client.get("/api/v1/jobs/doesnotexist")
    assert resp.status_code == 404


# ── With eager mode: full task execution ────────────────────────────────


def test_eager_scan_completes(client, _celery_eager):
    """In eager mode, dummy_scan runs synchronously inside POST.

    After the POST returns, the job should be status=success with
    progress_current=50, progress_total=50.
    """
    resp = client.post("/api/v1/jobs/scan")
    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    get_resp = client.get(f"/api/v1/jobs/{job_id}")
    data = get_resp.json()

    assert data["status"] == "success"
    assert data["progress_current"] == 50
    assert data["progress_total"] == 50
    assert data["progress_message"] == "Scan complete"


def test_eager_scan_progress_message_format(client, _celery_eager):
    """Verify the final progress_message is 'Scan complete'."""
    resp = client.post("/api/v1/jobs/scan")
    job_id = resp.json()["job_id"]

    job = job_db.get_job(job_id)
    assert job["progress_message"] == "Scan complete"
    assert job["updated_at"] >= job["created_at"]

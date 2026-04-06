from __future__ import annotations

import services.job_db as job_db
from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch


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

    app = FastAPI()
    app.include_router(jobs_router, prefix="/api/v1/jobs")
    return TestClient(app)


@pytest.fixture()
def search_client():
    from api.v1.search import router as search_router

    app = FastAPI()
    app.include_router(search_router, prefix="/api/v1/search")
    return TestClient(app)


@dataclass
class _FakeSearchHit:
    chunk_id: str
    file_id: str
    chunk_index: int
    file_path: str
    ext: str
    text: str
    score: float
    depth: str = "deep"
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def test_scan_records_missing_external_root_as_recoverable_issue(client, _celery_eager, tmp_path):
    missing_root = tmp_path / "detached_drive" / "documents"
    resp = client.post("/api/v1/jobs/scan", json={"folders": [str(missing_root)]})
    assert resp.status_code == 200

    job_id = resp.json()["job_id"]
    files = job_db.get_indexed_files(job_id=job_id)
    assert len(files) == 1
    assert files[0]["file_path"] == str(missing_root)
    assert files[0]["file_state"] == "MISSING_EXTERNALLY"
    assert files[0]["error_code"] == "MISSING_EXTERNALLY"
    assert "unavailable" in files[0]["error_message"].lower()


def test_search_results_include_metadata_block_from_index_state(search_client):
    fake_hits = [
        _FakeSearchHit(
            chunk_id="f1:0",
            file_id="f1",
            chunk_index=0,
            file_path="/Users/test/Documents/report.txt",
            ext=".txt",
            text="report body",
            score=0.93,
            depth="deep",
        )
    ]
    with patch("api.v1.search.pipeline.search", return_value=fake_hits), \
         patch("api.v1.search.is_under_root", return_value=True), \
         patch("api.v1.search.get_indexed_state_map", return_value={"f1": {"file_state": "INDEXED"}}), \
         patch(
             "api.v1.search.get_indexed_metadata_map",
             return_value={
                 "f1": {
                     "name": "report.txt",
                     "ext": ".txt",
                     "depth": "deep",
                     "engine": "mock",
                     "is_deletable": 0,
                     "tagged_os": 1,
                 }
             },
         ):
        resp = search_client.post("/api/v1/search", json={"query": "report"})

    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["metadata"]["name"] == "report.txt"
    assert result["metadata"]["ext"] == ".txt"
    assert result["metadata"]["depth"] == "deep"
    assert result["metadata"]["engine"] == "mock"
    assert result["metadata"]["is_deletable"] == 0
    assert result["metadata"]["tagged_os"] == 1

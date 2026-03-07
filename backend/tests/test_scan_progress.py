from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.job_db as job_db
from services.embedding import store


def _fake_embed_batch(texts):
    return [[0.01] * 3072 for _ in texts]


@pytest.fixture(autouse=True)
def _use_temp_db_and_store(tmp_path, monkeypatch):
    db_file = tmp_path / "test_jobs.db"
    monkeypatch.setattr(job_db, "_DB_PATH", db_file)
    monkeypatch.setenv("WISP_LANCEDB_PATH", str(tmp_path / "lancedb"))
    job_db.ensure_table()
    job_db.ensure_indexed_files_table()
    yield
    store.teardown()


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


def _scan(client: TestClient, root: Path) -> str:
    with patch("services.embedding.pipeline.embed_batch", side_effect=_fake_embed_batch):
        resp = client.post("/api/v1/jobs/scan", json={"folders": [str(root)]})
    assert resp.status_code == 200
    return resp.json()["job_id"]


def test_poll_job_exposes_stage(client, _celery_eager, tmp_path):
    root = tmp_path / "scan"
    root.mkdir()
    (root / "hello.txt").write_text("hello world")

    job_id = _scan(client, root)

    resp = client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()

    assert body["stage"] == "SCORED"


def test_poll_job_exposes_stats(client, _celery_eager, tmp_path):
    root = tmp_path / "scan"
    root.mkdir()
    (root / "hello.txt").write_text("hello world")

    job_id = _scan(client, root)

    resp = client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200
    body = resp.json()

    assert body["stats"]["discovered"] == 1
    assert body["stats"]["previewed"] == 1
    assert body["stats"]["embedded"] == 1
    assert body["stats"]["scored"] == 1
    assert body["stats"]["cached"] == 0
    assert body["stats"]["failed"] == 0


def test_rescan_unchanged_folder_reports_cached_files(client, _celery_eager, tmp_path):
    root = tmp_path / "scan"
    root.mkdir()
    (root / "hello.txt").write_text("hello world")

    first_job_id = _scan(client, root)
    second_job_id = _scan(client, root)

    first_job = job_db.get_job(first_job_id)
    second_job = job_db.get_job(second_job_id)
    second_rows = job_db.get_indexed_files(job_id=second_job_id)

    assert first_job["stats"]["cached"] == 0
    assert second_job["stats"]["cached"] == 1
    assert second_rows[0]["engine"] == "cached"


def test_changed_file_reindexes_without_duplicate_chunks(client, _celery_eager, tmp_path):
    root = tmp_path / "scan"
    root.mkdir()
    target = root / "hello.txt"
    target.write_text("hello world")

    _scan(client, root)
    first_count = store.collection_count()

    time.sleep(0.02)
    target.write_text("hello world\n" * 200)
    second_job_id = _scan(client, root)
    second_row = job_db.get_indexed_files(job_id=second_job_id)[0]

    assert second_row["engine"] != "cached"
    assert store.collection_count() == second_row["chunk_count"]
    assert store.collection_count() >= first_count


def test_progress_updates_are_monotonic_and_stage_ordered(client, _celery_eager, tmp_path):
    root = tmp_path / "scan"
    root.mkdir()
    (root / "a.txt").write_text("alpha")
    (root / "b.txt").write_text("beta")

    from tasks import scan as scan_task

    recorded: list[tuple[int, int, str | None]] = []
    real_update = scan_task.update_progress

    def _record(job_id, current, total, message, stage=None, stats=None):
        recorded.append((current, total, stage))
        return real_update(job_id, current, total, message, stage=stage, stats=stats)

    with patch("services.embedding.pipeline.embed_batch", side_effect=_fake_embed_batch), \
         patch.object(scan_task, "update_progress", side_effect=_record):
        resp = client.post("/api/v1/jobs/scan", json={"folders": [str(root)]})

    assert resp.status_code == 200
    currents = [current for current, _total, _stage in recorded]
    stages = [stage for _current, _total, stage in recorded if stage]

    assert currents == sorted(currents)
    assert stages[0] == "DISCOVERED"
    assert "PREVIEWED" in stages
    assert "EMBEDDED" in stages
    assert stages[-1] == "SCORED"


def test_rerun_after_partial_failure_does_not_duplicate_prior_good_state(
    client,
    _celery_eager,
    tmp_path,
):
    root = tmp_path / "scan"
    root.mkdir()
    (root / "a.txt").write_text("alpha")
    (root / "b.txt").write_text("beta")

    from services.embedding import pipeline as pipeline_module

    real_ingest = pipeline_module.ingest_file

    async def _fail_once(file_path, file_id=None, force_deep=False):
        if Path(file_path).name == "b.txt":
            raise RuntimeError("simulated interruption")
        return await real_ingest(file_path, file_id=file_id, force_deep=force_deep)

    with patch("services.embedding.pipeline.embed_batch", side_effect=_fake_embed_batch), \
         patch.object(pipeline_module, "ingest_file", side_effect=_fail_once):
        first_job_id = _scan(client, root)

    first_job = job_db.get_job(first_job_id)
    assert first_job["stats"]["failed"] == 1

    second_job_id = _scan(client, root)
    second_job = job_db.get_job(second_job_id)
    second_rows = job_db.get_indexed_files(job_id=second_job_id)

    assert second_job["stats"]["cached"] == 1
    assert second_job["stats"]["failed"] == 0
    assert {row["name"] for row in second_rows} == {"a.txt", "b.txt"}
    assert store.collection_count() == sum(row["chunk_count"] for row in second_rows)

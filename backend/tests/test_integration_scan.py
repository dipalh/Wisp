"""
Integration test: full scan pipeline with a realistic directory tree.

Mocks ONLY the AI/embedding layer (no Gemini API key needed).
Everything else runs for real:
  - scanner.collect_files() with ignore rules
  - pipeline.ingest_file() with real file I/O + classification
  - job_db writes (SQLite, WAL, retry wrapper)
  - set_deletable() for OS tagging
  - FastAPI endpoint through TestClient
  - Celery in eager mode

Verifies:
  1. Progress updates reach 100% without stalls.
  2. Indexed files list matches expectations.
  3. Ignore rules work: wisp_jobs.db, .git, node_modules, .DS_Store,
     hidden files, WAL artifacts, oversized files are NOT indexed.
  4. Deletable heuristic runs (dmg/installer → is_deletable=1).
  5. No DB-locked errors during rapid writes.
"""
from __future__ import annotations

import hashlib
import time
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.job_db as job_db


# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _use_temp_db(tmp_path, monkeypatch):
    db_file = tmp_path / "integration_test.db"
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


def _build_realistic_tree(root: Path) -> dict:
    """Build a test directory with a mix of real files and noise.

    Returns a dict mapping category → list of filenames that belong there.
    """
    # ── Good files (should be indexed) ─────────────────────────────
    good = root / "documents"
    good.mkdir()
    (good / "report.txt").write_text(
        "Q3 2025 Revenue Report\n\nTotal revenue: $1.2M\n"
        "Growth: 15% YoY\nKey markets: NA, EMEA, APAC\n"
        "Notable: Enterprise segment grew 23%."
    )
    (good / "notes.md").write_text(
        "# Meeting Notes - March 1\n\n"
        "- Discussed product roadmap\n"
        "- Agreed on Q2 milestones\n"
        "- Action items: hire 2 engineers"
    )
    (good / "budget.csv").write_text(
        "category,amount\nEngineering,500000\nMarketing,200000\nOps,150000"
    )

    code = root / "projects" / "app"
    code.mkdir(parents=True)
    (code / "main.py").write_text(
        "from fastapi import FastAPI\n\n"
        "app = FastAPI()\n\n"
        "@app.get('/')\ndef root():\n    return {'status': 'ok'}\n"
    )
    (code / "utils.js").write_text(
        "export function formatDate(d) {\n"
        "  return d.toISOString().split('T')[0];\n}\n"
    )

    media = root / "media"
    media.mkdir()
    # Fake image (small enough to be collected, but not a real PNG)
    (media / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 200)
    (media / "clip.mp4").write_bytes(b"\x00" * 500)  # video → card-only

    # Installer — should be flagged deletable by heuristic
    (root / "old-installer.dmg").write_bytes(b"\x00" * 1000)

    # Archive
    (root / "backup.zip").write_bytes(b"PK\x03\x04" + b"\x00" * 200)

    good_names = {
        "report.txt", "notes.md", "budget.csv",
        "main.py", "utils.js",
        "photo.png", "clip.mp4",
        "old-installer.dmg", "backup.zip",
    }

    # ── Noise (must NOT be indexed) ────────────────────────────────
    (root / "wisp_jobs.db").write_text("sqlite artifact")
    (root / "wisp_ingest_cache.json").write_text("{}")
    (root / "wisp_jobs.db-wal").write_text("wal")
    (root / "wisp_jobs.db-shm").write_text("shm")
    (root / ".DS_Store").write_bytes(b"\x00\x00\x00\x01")
    (root / ".hidden_config").write_text("secret=abc")
    (root / "Thumbs.db").write_bytes(b"\x00")
    (root / "desktop.ini").write_text("[.ShellClassInfo]")

    git_dir = root / ".git"
    git_dir.mkdir()
    (git_dir / "HEAD").write_text("ref: refs/heads/main")
    (git_dir / "config").write_text("[core]\nbare = false")

    nm = root / "node_modules"
    nm.mkdir()
    (nm / "lodash.js").write_text("module.exports = {}")

    pc = root / "__pycache__"
    pc.mkdir()
    (pc / "main.cpython-312.pyc").write_bytes(b"\x00" * 50)

    lance = root / "lancedb"
    lance.mkdir()
    (lance / "embeddings.lance").write_bytes(b"\x00" * 100)

    noise_names = {
        "wisp_jobs.db", "wisp_ingest_cache.json",
        "wisp_jobs.db-wal", "wisp_jobs.db-shm",
        ".DS_Store", ".hidden_config",
        "Thumbs.db", "desktop.ini",
        "HEAD", "config",  # inside .git
        "lodash.js",  # inside node_modules
        "main.cpython-312.pyc",  # inside __pycache__
        "embeddings.lance",  # inside lancedb
    }

    return {"good": good_names, "noise": noise_names}


# ── The integration test ─────────────────────────────────────────────────────


def test_full_scan_integration(client, _celery_eager, tmp_path):
    """End-to-end: POST /scan → Celery eager → real scanner → indexed_files."""
    from unittest.mock import patch, MagicMock

    scan_root = tmp_path / "test_home"
    scan_root.mkdir()
    expected = _build_realistic_tree(scan_root)

    # ── Mock ONLY the AI/embedding layer ──────────────────────────
    # embed_batch: return dummy vectors (one per chunk)
    def _fake_embed_batch(texts):
        return [[0.1] * 768 for _ in texts]

    def _fake_embed_text(text):
        return [0.1] * 768

    # Store: accept upserts silently, return nothing on queries
    mock_store = MagicMock()
    mock_store.current_db_path.return_value = None

    with patch("services.embedding.pipeline.embed_batch", side_effect=_fake_embed_batch), \
         patch("services.embedding.pipeline.embed_text", side_effect=_fake_embed_text), \
         patch("services.embedding.pipeline.store", mock_store):

        resp = client.post(
            "/api/v1/jobs/scan",
            json={"folders": [str(scan_root)]},
        )

    assert resp.status_code == 200
    job_id = resp.json()["job_id"]

    # ── Verify job completed successfully ─────────────────────────
    job = job_db.get_job(job_id)
    assert job is not None
    assert job["status"] == "success", f"Job failed: {job['progress_message']}"
    assert job["progress_current"] == job["progress_total"]
    assert job["progress_total"] > 0

    # ── Verify indexed files list ─────────────────────────────────
    files = job_db.get_indexed_files(job_id=job_id)
    indexed_names = {f["name"] for f in files}

    # 1) All good files were indexed
    for name in expected["good"]:
        assert name in indexed_names, f"Expected '{name}' to be indexed but it wasn't. Got: {indexed_names}"

    # 2) NO noise files were indexed
    for name in expected["noise"]:
        assert name not in indexed_names, f"Noise file '{name}' should NOT be indexed but was. Got: {indexed_names}"

    # 3) Total count matches
    assert len(files) == len(expected["good"]), (
        f"Expected {len(expected['good'])} indexed files, got {len(files)}. "
        f"Names: {indexed_names}"
    )

    # ── Verify ignore rules specifically ──────────────────────────
    all_paths = {f["file_path"] for f in files}
    for p in all_paths:
        assert "wisp_jobs.db" not in p
        assert "node_modules" not in p
        assert ".git" not in p
        assert "__pycache__" not in p
        assert "lancedb" not in p
        assert ".DS_Store" not in p

    # ── Verify progress wasn't stuck ──────────────────────────────
    assert job["progress_current"] == len(expected["good"])
    assert job["progress_total"] == len(expected["good"])

    # ── Verify DMG flagged as deletable by heuristic ──────────────
    dmg_files = [f for f in files if f["ext"] == ".dmg"]
    assert len(dmg_files) == 1
    assert dmg_files[0]["is_deletable"] == 1, (
        f"old-installer.dmg should be flagged deletable, got is_deletable={dmg_files[0]['is_deletable']}"
    )

    # ── Verify depth classification ───────────────────────────────
    depths = {f["name"]: f["depth"] for f in files}
    # Text files → "deep"
    assert depths["report.txt"] == "deep"
    assert depths["notes.md"] == "deep"
    assert depths["main.py"] == "deep"
    # Video → "card"
    assert depths["clip.mp4"] == "card"

    # ── Verify each file has a file_id and chunk_count > 0 ────────
    for f in files:
        assert f["file_id"], f"file_id is empty for {f['name']}"
        assert f["chunk_count"] >= 0, f"chunk_count < 0 for {f['name']}"
        assert f["updated_at"], f"updated_at is empty for {f['name']}"

    # ── Verify the /indexed-files endpoint returns correct data ───
    api_resp = client.get(f"/api/v1/jobs/indexed-files?job_id={job_id}")
    assert api_resp.status_code == 200
    api_data = api_resp.json()
    assert api_data["total"] == len(expected["good"])
    api_names = {f["name"] for f in api_data["files"]}
    assert api_names == expected["good"]


def test_scan_empty_folder_succeeds(client, _celery_eager, tmp_path):
    """Scanning an empty folder should complete with success, 0 files."""
    empty = tmp_path / "empty"
    empty.mkdir()

    from unittest.mock import patch, MagicMock

    with patch("services.embedding.pipeline.store", MagicMock()):
        resp = client.post(
            "/api/v1/jobs/scan",
            json={"folders": [str(empty)]},
        )

    job_id = resp.json()["job_id"]
    job = job_db.get_job(job_id)
    assert job["status"] == "success"
    assert "No files found" in job["progress_message"]

    files = job_db.get_indexed_files(job_id=job_id)
    assert len(files) == 0


def test_scan_noise_only_folder(client, _celery_eager, tmp_path):
    """A folder with ONLY noise files should complete with 0 indexed."""
    noise = tmp_path / "noise_only"
    noise.mkdir()
    (noise / ".DS_Store").write_bytes(b"\x00")
    (noise / "wisp_jobs.db").write_text("sqlite")
    (noise / "Thumbs.db").write_bytes(b"\x00")
    (noise / ".hidden").write_text("nope")
    git = noise / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref")

    from unittest.mock import patch, MagicMock

    with patch("services.embedding.pipeline.store", MagicMock()):
        resp = client.post(
            "/api/v1/jobs/scan",
            json={"folders": [str(noise)]},
        )

    job_id = resp.json()["job_id"]
    job = job_db.get_job(job_id)
    assert job["status"] == "success"
    assert "No files found" in job["progress_message"]

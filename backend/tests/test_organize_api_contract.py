from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.actions as action_store
from services.organizer.models import DirectorySuggestions
from services.organizer.proposal_state import clear as clear_proposals
from services.roots import clear as clear_roots


@pytest.fixture(autouse=True)
def _clean_state(tmp_path):
    clear_roots()
    clear_proposals()
    action_store.configure_db(tmp_path / "actions.db")
    action_store.clear()
    yield
    action_store.clear()
    clear_proposals()
    clear_roots()


def _client() -> TestClient:
    from api.v1.organize import router as organize_router

    app = FastAPI()
    app.include_router(organize_router, prefix="/organize")
    return TestClient(app)


def test_post_organize_proposals_returns_strategy_envelope():
    client = _client()
    mocked = DirectorySuggestions.model_validate(
        {
            "proposals": [
                {
                    "name": "By Project",
                    "rationale": "Organize by project folders.",
                    "reasons": ["Shared project context"],
                    "citations": ["/workspace/root/docs/report.txt"],
                    "folder_tree": ["Projects/Alpha/"],
                    "mappings": [
                        {
                            "original_path": "/workspace/root/docs/report.txt",
                            "suggested_path": "Projects/Alpha/report.txt",
                        }
                    ],
                }
            ],
            "recommendation": "Use By Project for clearer context.",
        }
    )
    with patch("api.v1.organize.suggest_directories", new=AsyncMock(return_value=mocked)):
        resp = client.post("/organize/proposals", json={"mock_mode": True})

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert len(body["strategies"]) == 1
    assert body["recommendation"] == "Use By Project for clearer context."


def test_post_organize_proposals_forwards_root_path_to_suggester():
    client = _client()
    mocked = DirectorySuggestions.model_validate(
        {
            "proposals": [],
            "recommendation": "Nothing to do.",
        }
    )
    with patch("api.v1.organize.suggest_directories", new=AsyncMock(return_value=mocked)) as mocked_suggester:
        resp = client.post(
            "/organize/proposals",
            json={"mock_mode": True, "root_path": "/workspace/root"},
        )

    assert resp.status_code == 200
    mocked_suggester.assert_awaited_once_with(
        mock_mode=True,
        tool_budget=None,
        root_path="/workspace/root",
    )


def test_post_organize_batches_apply_route_contract(tmp_path):
    client = _client()
    src = tmp_path / "a.txt"
    src.write_text("hello")
    dst = tmp_path / "b.txt"
    accept = client.post(
        "/organize/proposals/proposal-batch/accept",
        json={"mappings": [{"original_path": str(src), "suggested_path": str(dst)}]},
    )
    assert accept.status_code == 200
    batch_id = accept.json()["batch_id"]

    apply = client.post(f"/organize/batches/{batch_id}/apply")
    assert apply.status_code == 200
    body = apply.json()
    assert body["ok"] is True
    assert body["batch_id"] == batch_id
    assert body["status"] == "APPLIED"
    assert body["applied"] == 1
    assert body["failed"] == 0
    assert body["partial"] is False
    assert len(body["details"]) == 1
    assert not src.exists()
    assert dst.exists()


def test_post_organize_batches_undo_route_contract(tmp_path):
    client = _client()
    src = tmp_path / "a.txt"
    src.write_text("hello")
    dst = tmp_path / "b.txt"
    accept = client.post(
        "/organize/proposals/proposal-batch-undo/accept",
        json={"mappings": [{"original_path": str(src), "suggested_path": str(dst)}]},
    )
    assert accept.status_code == 200
    batch_id = accept.json()["batch_id"]

    apply = client.post(f"/organize/batches/{batch_id}/apply")
    assert apply.status_code == 200

    undo = client.post(f"/organize/batches/{batch_id}/undo")
    assert undo.status_code == 200
    body = undo.json()
    assert body["ok"] is True
    assert body["batch_id"] == batch_id
    assert body["status"] == "UNDONE"
    assert body["undone"] == 1
    assert body["failed"] == 0
    assert body["partial"] is False
    assert len(body["details"]) == 1
    assert src.exists()
    assert not dst.exists()


def test_post_organize_batches_apply_route_returns_partial_details(tmp_path):
    client = _client()
    source_ok = tmp_path / "ok.txt"
    source_ok.write_text("hello")
    destination_ok = tmp_path / "organized" / "ok.txt"

    source_collision = tmp_path / "collision.txt"
    source_collision.write_text("keep")
    destination_collision = tmp_path / "organized" / "collision.txt"
    destination_collision.parent.mkdir(parents=True, exist_ok=True)
    destination_collision.write_text("already here")

    accept = client.post(
        "/organize/proposals/proposal-batch-partial/accept",
        json={
            "mappings": [
                {"original_path": str(source_ok), "suggested_path": str(destination_ok)},
                {"original_path": str(source_collision), "suggested_path": str(destination_collision)},
            ]
        },
    )
    assert accept.status_code == 200
    batch_id = accept.json()["batch_id"]

    apply = client.post(f"/organize/batches/{batch_id}/apply")
    assert apply.status_code == 200
    body = apply.json()
    assert body["ok"] is True
    assert body["batch_id"] == batch_id
    assert body["partial"] is True
    assert body["applied"] == 1
    assert body["failed"] == 1
    assert len(body["details"]) == 2
    assert source_ok.exists() is False
    assert destination_ok.exists() is True


def test_post_organize_batches_undo_route_returns_partial_details(tmp_path):
    client = _client()
    source_one = tmp_path / "one.txt"
    source_two = tmp_path / "two.txt"
    source_one.write_text("one")
    source_two.write_text("two")
    destination_one = tmp_path / "organized" / "one.txt"
    destination_two = tmp_path / "organized" / "two.txt"

    accept = client.post(
        "/organize/proposals/proposal-batch-partial-undo/accept",
        json={
            "mappings": [
                {"original_path": str(source_one), "suggested_path": str(destination_one)},
                {"original_path": str(source_two), "suggested_path": str(destination_two)},
            ]
        },
    )
    assert accept.status_code == 200
    batch_id = accept.json()["batch_id"]

    apply = client.post(f"/organize/batches/{batch_id}/apply")
    assert apply.status_code == 200
    destination_two.unlink()

    undo = client.post(f"/organize/batches/{batch_id}/undo")
    assert undo.status_code == 200
    body = undo.json()
    assert body["ok"] is True
    assert body["batch_id"] == batch_id
    assert body["partial"] is True
    assert body["undone"] == 1
    assert body["failed"] == 1
    assert len(body["details"]) == 2
    assert source_one.exists() is True

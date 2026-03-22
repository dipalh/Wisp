from __future__ import annotations

from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.organizer.models import DirectorySuggestions


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


def test_post_organize_batches_apply_route_contract():
    client = _client()
    accept = client.post(
        "/organize/proposals/proposal-batch/accept",
        json={"mappings": [{"original_path": "/tmp/a.txt", "suggested_path": "/tmp/b.txt"}]},
    )
    assert accept.status_code == 200
    batch_id = accept.json()["batch_id"]

    apply = client.post(f"/organize/batches/{batch_id}/apply")
    assert apply.status_code == 200
    assert apply.json() == {"ok": True, "batch_id": batch_id, "applied": True}


def test_post_organize_batches_undo_route_contract():
    client = _client()
    accept = client.post(
        "/organize/proposals/proposal-batch-undo/accept",
        json={"mappings": [{"original_path": "/tmp/a.txt", "suggested_path": "/tmp/b.txt"}]},
    )
    assert accept.status_code == 200
    batch_id = accept.json()["batch_id"]

    undo = client.post(f"/organize/batches/{batch_id}/undo")
    assert undo.status_code == 200
    assert undo.json() == {"ok": True, "batch_id": batch_id, "undone": True}

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

import services.actions as action_store
from services.roots import add_root, clear as clear_roots
from services.organizer.models import DirectoryProposal, DirectorySuggestions
from services.organizer.suggester import suggest_directories


@pytest.fixture(autouse=True)
def _clean_roots():
    from services.organizer.batch_state import clear as clear_batches
    from services.organizer.proposal_state import clear as clear_proposals

    clear_roots()
    clear_batches()
    clear_proposals()
    yield
    clear_roots()
    clear_batches()
    clear_proposals()


def test_organize_proposal_requires_citations_and_reasons():
    with pytest.raises(ValidationError):
        DirectoryProposal(
            name="By Project",
            rationale="Group files by shared project context.",
            folder_tree=["Projects/Alpha/"],
            mappings=[
                {
                    "original_path": "/tmp/root/report.txt",
                    "suggested_path": "Projects/Alpha/report.txt",
                }
            ],
        )


def test_organize_mock_mode_deterministic_for_same_fixture(monkeypatch):
    fixture_files = [
        {
            "file_path": "/workspace/root/docs/report.txt",
            "ext": ".txt",
            "text": "Quarterly report",
        },
        {
            "file_path": "/workspace/root/media/photo.png",
            "ext": ".png",
            "text": "Trip photo",
        },
    ]
    monkeypatch.setattr("services.organizer.suggester.store.list_files", lambda: fixture_files)

    first = asyncio.run(suggest_directories(mock_mode=True))
    second = asyncio.run(suggest_directories(mock_mode=True))

    assert first.model_dump() == second.model_dump()
    assert len(first.proposals) >= 1


def test_organize_tool_budget_exhaustion_returns_degraded_response(monkeypatch):
    fixture_files = [
        {
            "file_path": "/workspace/root/docs/report.txt",
            "ext": ".txt",
            "text": "Quarterly report",
        }
    ]
    monkeypatch.setattr("services.organizer.suggester.store.list_files", lambda: fixture_files)

    result = asyncio.run(suggest_directories(mock_mode=True, tool_budget=0))

    assert result.proposals == []
    assert "degraded" in result.recommendation.lower()
    assert "budget" in result.recommendation.lower()


def test_organize_rejects_targets_outside_roots(monkeypatch, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    add_root(str(root))

    fixture_files = [
        {
            "file_path": str(root / "inside.txt"),
            "ext": ".txt",
            "text": "inside",
        },
        {
            "file_path": str(outside / "escape.txt"),
            "ext": ".txt",
            "text": "outside",
        },
    ]
    monkeypatch.setattr("services.organizer.suggester.store.list_files", lambda: fixture_files)

    result = asyncio.run(suggest_directories(mock_mode=True))

    assert result.proposals == []
    assert "outside registered roots" in result.recommendation.lower()


def test_organize_proposals_returns_no_mutation_side_effects():
    from api.v1.organize import router as organize_router

    app = FastAPI()
    app.include_router(organize_router, prefix="/organize")
    client = TestClient(app)
    action_store.clear()

    mocked = DirectorySuggestions.model_validate(
        {
            "proposals": [
                {
                    "name": "By Project",
                    "rationale": "Organize by project folders.",
                    "reasons": ["Shared project context", "Safer review workflow"],
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
        resp = client.get("/organize/suggestions")

    assert resp.status_code == 200
    assert action_store.get_all() == []


def test_organize_accept_required_before_apply():
    from api.v1.organize import router as organize_router

    app = FastAPI()
    app.include_router(organize_router, prefix="/organize")
    client = TestClient(app)

    proposal_id = "proposal-123"

    pre = client.post(f"/organize/proposals/{proposal_id}/apply")
    assert pre.status_code == 409
    assert pre.json()["detail"]["code"] == "ORGANIZE_ACCEPT_REQUIRED"

    accept = client.post(f"/organize/proposals/{proposal_id}/accept")
    assert accept.status_code == 200
    accept_body = accept.json()
    assert accept_body["ok"] is True
    assert accept_body["proposal_id"] == proposal_id
    assert accept_body["accepted"] is True
    assert "batch_id" in accept_body

    post = client.post(f"/organize/proposals/{proposal_id}/apply")
    assert post.status_code == 200
    assert post.json() == {"ok": True, "proposal_id": proposal_id, "applied": True}


def test_organize_apply_handles_destination_collision_deterministically(tmp_path):
    from api.v1.organize import router as organize_router

    app = FastAPI()
    app.include_router(organize_router, prefix="/organize")
    client = TestClient(app)

    src = tmp_path / "source.txt"
    src.write_text("keep")
    dst = tmp_path / "existing.txt"
    dst.write_text("already here")

    proposal_id = "proposal-collision"
    accept = client.post(
        f"/organize/proposals/{proposal_id}/accept",
        json={
            "mappings": [
                {
                    "original_path": str(src),
                    "suggested_path": str(dst),
                }
            ]
        },
    )
    assert accept.status_code == 200

    apply = client.post(f"/organize/proposals/{proposal_id}/apply")
    assert apply.status_code == 409
    assert apply.json()["detail"]["code"] == "DESTINATION_COLLISION"
    assert str(dst) in apply.json()["detail"]["message"]


def test_organize_undo_batch_restores_previous_paths(tmp_path):
    from api.v1.organize import router as organize_router

    app = FastAPI()
    app.include_router(organize_router, prefix="/organize")
    client = TestClient(app)

    src = tmp_path / "source.txt"
    src.write_text("keep")
    dst = tmp_path / "moved.txt"

    proposal_id = "proposal-undo"
    accept = client.post(
        f"/organize/proposals/{proposal_id}/accept",
        json={
            "mappings": [
                {
                    "original_path": str(src),
                    "suggested_path": str(dst),
                }
            ]
        },
    )
    assert accept.status_code == 200

    apply = client.post(f"/organize/proposals/{proposal_id}/apply")
    assert apply.status_code == 200
    assert not src.exists()
    assert dst.exists()

    undo = client.post(f"/organize/proposals/{proposal_id}/undo")
    assert undo.status_code == 200
    assert undo.json() == {"ok": True, "proposal_id": proposal_id, "undone": True}
    assert src.exists()
    assert not dst.exists()


def test_organize_ollama_unavailable_falls_back_to_deterministic_mock_strategy(monkeypatch):
    fixture_files = [
        {
            "file_path": "/workspace/root/docs/report.txt",
            "ext": ".txt",
            "text": "Quarterly report",
        },
        {
            "file_path": "/workspace/root/media/photo.png",
            "ext": ".png",
            "text": "Trip photo",
        },
    ]
    monkeypatch.setattr("services.organizer.suggester.store.list_files", lambda: fixture_files)

    with patch(
        "services.organizer.suggester.generate_structured",
        new=AsyncMock(side_effect=RuntimeError("ollama unavailable")),
    ):
        degraded = asyncio.run(suggest_directories())

    deterministic = asyncio.run(suggest_directories(mock_mode=True))

    assert degraded.proposals == deterministic.proposals
    assert "degraded" in degraded.recommendation.lower()
    assert "ollama" in degraded.recommendation.lower()

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.actions as action_store
from services.actions.models import ActionStatus, ActionType
from services.roots import add_root, clear as clear_roots


def _client() -> TestClient:
    from api.v1.organize import router as organize_router

    app = FastAPI()
    app.include_router(organize_router, prefix="/organize")
    return TestClient(app)


def test_accept_organize_proposal_creates_durable_action_batch(tmp_path):
    action_store.configure_db(tmp_path / "actions.db")
    action_store.clear()
    clear_roots()
    add_root(str(tmp_path))
    client = _client()

    src = tmp_path / "source.txt"
    src.write_text("hello")
    dst = tmp_path / "organized" / "source.txt"

    response = client.post(
        "/organize/proposals/proposal-durable/accept",
        json={
            "mappings": [
                {
                    "original_path": str(src),
                    "suggested_path": str(dst),
                }
            ]
        },
    )

    assert response.status_code == 200
    body = response.json()
    batch = action_store.get_batch(body["batch_id"])

    assert batch is not None
    assert batch["proposal_id"] == "proposal-durable"
    assert len(batch["action_ids"]) == 1

    recorded = action_store.get(batch["action_ids"][0])
    assert recorded is not None
    assert recorded.type == ActionType.MOVE
    assert recorded.status == ActionStatus.ACCEPTED
    assert recorded.proposal_id == "proposal-durable"
    assert recorded.before_state["path"] == str(src)
    assert recorded.after_state["path"] == str(dst)


def test_proposal_apply_and_undo_run_through_durable_action_engine(tmp_path):
    action_store.configure_db(tmp_path / "actions.db")
    action_store.clear()
    clear_roots()
    add_root(str(tmp_path))
    client = _client()

    src = tmp_path / "source.txt"
    src.write_text("hello")
    dst = tmp_path / "organized" / "source.txt"

    accept = client.post(
        "/organize/proposals/proposal-apply/accept",
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
    batch_id = accept.json()["batch_id"]

    apply = client.post("/organize/proposals/proposal-apply/apply")
    assert apply.status_code == 200
    assert src.exists() is False
    assert dst.exists() is True

    batch = action_store.get_batch(batch_id)
    assert batch is not None
    assert batch["status"] == ActionStatus.APPLIED.value
    applied_action = action_store.get(batch["action_ids"][0])
    assert applied_action is not None
    assert applied_action.status == ActionStatus.APPLIED

    undo = client.post("/organize/proposals/proposal-apply/undo")
    assert undo.status_code == 200
    assert src.exists() is True
    assert dst.exists() is False

    undone_action = action_store.get(batch["action_ids"][0])
    assert undone_action is not None
    assert undone_action.status == ActionStatus.UNDONE

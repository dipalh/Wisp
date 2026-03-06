from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.actions as action_store
from services.actions.executor import ExecutionError, execute_action
from services.actions.models import Action, ActionStatus, ActionType
from services.roots import add_root, clear as clear_roots


@pytest.fixture(autouse=True)
def _clean_state():
    clear_roots()
    action_store.clear()
    yield
    clear_roots()
    action_store.clear()


def _move_action(src: Path, dst: Path) -> Action:
    return action_store.add(
        Action(
            type=ActionType.MOVE,
            label=f"Move {src.name}",
            targets=[str(src)],
            before_state={"path": str(src)},
            after_state={"path": str(dst)},
            status=ActionStatus.PROPOSED,
        )
    )


def test_execute_action_rejects_destination_outside_registered_root(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    src = root / "keep.txt"
    src.write_text("keep")
    dst = outside / "moved.txt"
    add_root(str(root))

    action = _move_action(src, dst)

    with pytest.raises(ExecutionError, match="Destination path is not under any registered root"):
        execute_action(action.id)

    assert src.exists()
    assert not dst.exists()
    assert action_store.get(action.id).status == ActionStatus.PROPOSED


def test_apply_endpoint_rejects_destination_outside_registered_root(tmp_path):
    from api.v1.actions import router as actions_router

    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    src = root / "keep.txt"
    src.write_text("keep")
    dst = outside / "moved.txt"
    add_root(str(root))
    action = _move_action(src, dst)

    app = FastAPI()
    app.include_router(actions_router, prefix="/actions")
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post(f"/actions/{action.id}/apply")

    assert resp.status_code == 422
    assert "Destination path is not under any registered root" in resp.text


def test_execute_action_rejects_destination_collision_with_stable_code(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    src = root / "source.txt"
    src.write_text("keep")
    dst = root / "existing.txt"
    dst.write_text("already here")
    add_root(str(root))

    action = _move_action(src, dst)

    with pytest.raises(ExecutionError, match="DESTINATION_COLLISION"):
        execute_action(action.id)

    assert src.exists()
    assert dst.read_text() == "already here"
    assert action_store.get(action.id).status == ActionStatus.PROPOSED


def test_apply_endpoint_returns_collision_code(tmp_path):
    from api.v1.actions import router as actions_router

    root = tmp_path / "root"
    root.mkdir()
    src = root / "source.txt"
    src.write_text("keep")
    dst = root / "existing.txt"
    dst.write_text("already here")
    add_root(str(root))
    action = _move_action(src, dst)

    app = FastAPI()
    app.include_router(actions_router, prefix="/actions")
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.post(f"/actions/{action.id}/apply")

    assert resp.status_code == 409
    body = resp.json()
    assert body["detail"]["code"] == "DESTINATION_COLLISION"
    assert "already exists" in body["detail"]["message"]

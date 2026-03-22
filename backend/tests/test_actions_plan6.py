from __future__ import annotations

import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from services.actions.executor import execute_action
from services.actions.models import Action, ActionStatus, ActionType
from services.roots import add_root
from services.roots import clear as clear_roots


@pytest.fixture(autouse=True)
def _isolated_action_store(tmp_path):
    from services.actions import store as action_store

    action_store.configure_db(tmp_path / "actions_test.db")
    action_store.clear()
    clear_roots()
    yield
    action_store.clear()
    clear_roots()


def test_action_store_persists_across_module_reload(tmp_path):
    from services.actions import store as action_store

    db_path = tmp_path / "actions_plan6.db"
    action_store.configure_db(db_path)
    action_store.clear()
    clear_roots()

    action = Action(
        type=ActionType.MOVE,
        label="Move keep.txt",
        targets=["/tmp/keep.txt"],
        before_state={"path": "/tmp/keep.txt"},
        after_state={"path": "/tmp/archive/keep.txt"},
        status=ActionStatus.PROPOSED,
    )
    action_store.add(action)

    reloaded = importlib.reload(action_store)
    reloaded.configure_db(db_path)

    persisted = reloaded.get(action.id)
    assert persisted is not None
    assert persisted.id == action.id
    assert persisted.status == ActionStatus.PROPOSED


def _make_move_action(src: str, dst: str, *, status: ActionStatus = ActionStatus.PROPOSED) -> Action:
    return Action(
        type=ActionType.MOVE,
        label=f"Move {src}",
        targets=[src],
        before_state={"path": src},
        after_state={"path": dst},
        status=status,
    )


def test_delete_action_moves_file_to_quarantine_instead_of_hard_delete(tmp_path):
    from services.actions import store as action_store

    root = tmp_path / "root"
    root.mkdir()
    add_root(str(root))
    src = root / "delete_me.txt"
    src.write_text("remove this safely")

    action = Action(
        type=ActionType.DELETE,
        label="Delete delete_me.txt",
        targets=[str(src)],
        before_state={"path": str(src)},
        after_state={},
        status=ActionStatus.PROPOSED,
    )
    action_store.add(action)

    result = execute_action(action.id)
    persisted = action_store.get(action.id)

    assert result.status == ActionStatus.APPLIED
    assert persisted is not None
    assert not src.exists()
    quarantine_path = persisted.after_state.get("path", "")
    assert ".wisp_quarantine" in quarantine_path
    assert (root / ".wisp_quarantine").exists()
    assert quarantine_path.endswith("delete_me.txt")


def test_action_status_lifecycle_includes_plan6_states():
    values = {status.value for status in ActionStatus}
    assert {"PROPOSED", "ACCEPTED", "APPLIED", "FAILED", "UNDONE", "PARTIAL"} <= values


def test_delete_action_can_be_undone_from_quarantine(tmp_path):
    from api.v1.actions import router as actions_router
    from services.actions import store as action_store

    app = FastAPI()
    app.include_router(actions_router, prefix="/actions")
    client = TestClient(app, raise_server_exceptions=False)

    root = tmp_path / "root"
    root.mkdir()
    add_root(str(root))
    src = root / "delete_and_restore.txt"
    src.write_text("restore me")

    action = Action(
        type=ActionType.DELETE,
        label="Delete delete_and_restore.txt",
        targets=[str(src)],
        before_state={"path": str(src)},
        after_state={},
        status=ActionStatus.PROPOSED,
    )
    action_store.add(action)
    execute_action(action.id)

    undo = client.post(f"/actions/{action.id}/undo")
    assert undo.status_code == 200
    assert undo.json()["status"] == "UNDONE"
    assert src.exists()


def test_apply_batch_returns_partial_with_per_target_results(tmp_path):
    from api.v1.actions import router as actions_router
    from services.actions import store as action_store

    app = FastAPI()
    app.include_router(actions_router, prefix="/actions")
    client = TestClient(app, raise_server_exceptions=False)

    root = tmp_path / "root"
    root.mkdir()
    add_root(str(root))

    src_ok = root / "ok.txt"
    src_ok.write_text("ok")
    dst_ok = root / "dest" / "ok.txt"

    src_missing = root / "missing.txt"
    dst_missing = root / "dest" / "missing.txt"

    ok_action = action_store.add(
        _make_move_action(str(src_ok), str(dst_ok), status=ActionStatus.ACCEPTED)
    )
    missing_action = action_store.add(
        _make_move_action(str(src_missing), str(dst_missing), status=ActionStatus.ACCEPTED)
    )

    batch = action_store.create_batch(
        [ok_action.id, missing_action.id],
        proposal_id="proposal-plan6",
        actor="tester",
    )

    resp = client.post(f"/actions/batches/{batch['batch_id']}/apply")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "PARTIAL"
    assert body["applied"] == 1
    assert body["failed"] == 1
    assert len(body["details"]) == 2
    assert {d["status"] for d in body["details"]} == {"APPLIED", "FAILED"}


def test_undo_batch_returns_partial_when_some_actions_cannot_be_reversed(tmp_path):
    from api.v1.actions import router as actions_router
    from services.actions import store as action_store

    app = FastAPI()
    app.include_router(actions_router, prefix="/actions")
    client = TestClient(app, raise_server_exceptions=False)

    root = tmp_path / "root"
    root.mkdir()
    add_root(str(root))

    src_ok = root / "undo_ok.txt"
    src_ok.write_text("undo me")
    dst_ok = root / "dest" / "undo_ok.txt"

    src_never_applied = root / "never_applied.txt"
    dst_never_applied = root / "dest" / "never_applied.txt"

    ok_action = action_store.add(
        _make_move_action(str(src_ok), str(dst_ok), status=ActionStatus.ACCEPTED)
    )
    failed_action = action_store.add(
        _make_move_action(
            str(src_never_applied),
            str(dst_never_applied),
            status=ActionStatus.FAILED,
        )
    )

    batch = action_store.create_batch(
        [ok_action.id, failed_action.id],
        proposal_id="proposal-plan6-undo",
        actor="tester",
    )
    apply = client.post(f"/actions/batches/{batch['batch_id']}/apply")
    assert apply.status_code == 200

    undo = client.post(f"/actions/batches/{batch['batch_id']}/undo")
    assert undo.status_code == 200
    body = undo.json()
    assert body["status"] == "PARTIAL"
    assert body["undone"] == 1
    assert body["failed"] == 1
    assert len(body["details"]) == 2


def test_undo_batch_missing_file_yields_partial_with_deterministic_failure_code(tmp_path):
    from api.v1.actions import router as actions_router
    from services.actions import store as action_store

    app = FastAPI()
    app.include_router(actions_router, prefix="/actions")
    client = TestClient(app, raise_server_exceptions=False)

    root = tmp_path / "root"
    root.mkdir()
    add_root(str(root))

    src1 = root / "present.txt"
    src2 = root / "will_be_missing.txt"
    src1.write_text("one")
    src2.write_text("two")
    dst1 = root / "dest" / "present.txt"
    dst2 = root / "dest" / "will_be_missing.txt"

    action1 = action_store.add(_make_move_action(str(src1), str(dst1), status=ActionStatus.ACCEPTED))
    action2 = action_store.add(_make_move_action(str(src2), str(dst2), status=ActionStatus.ACCEPTED))
    batch = action_store.create_batch([action1.id, action2.id], proposal_id="proposal-missing-undo", actor="tester")

    apply = client.post(f"/actions/batches/{batch['batch_id']}/apply")
    assert apply.status_code == 200
    assert dst2.exists()

    # Simulate external mutation before undo.
    dst2.unlink()

    undo = client.post(f"/actions/batches/{batch['batch_id']}/undo")
    assert undo.status_code == 200
    body = undo.json()
    assert body["status"] == "PARTIAL"
    assert body["undone"] == 1
    assert body["failed"] == 1
    failed_detail = [d for d in body["details"] if d["status"] == "FAILED"][0]
    assert failed_detail["code"] == "UNDO_SOURCE_MISSING"


def test_apply_batch_unknown_action_id_reports_failure_without_500(tmp_path):
    from api.v1.actions import router as actions_router
    from services.actions import store as action_store

    app = FastAPI()
    app.include_router(actions_router, prefix="/actions")
    client = TestClient(app, raise_server_exceptions=False)

    batch = action_store.create_batch(["missing-action-id"], proposal_id="proposal-unknown", actor="tester")
    resp = client.post(f"/actions/batches/{batch['batch_id']}/apply")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "FAILED"
    assert body["applied"] == 0
    assert body["failed"] == 1
    assert body["details"][0]["code"] == "ACTION_NOT_FOUND"

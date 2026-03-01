"""
Action Executor — Test Suite

Run from backend/:
    python -m tests.test_executor
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path

import services.actions as action_store
from services.actions.executor import ExecutionError, execute_action
from services.actions.models import Action, ActionStatus, ActionType
from services.roots import add_root, clear as clear_roots

_pass = 0
_fail = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _pass, _fail
    status = "[PASS]" if condition else "[FAIL]"
    print(f"  {status}  {name}")
    if detail:
        print(f"         {detail}")
    if condition:
        _pass += 1
    else:
        _fail += 1


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_file(content: bytes = b"test content", suffix: str = ".txt") -> Path:
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.write(content)
    f.close()
    return Path(f.name)


def _make_move_action(src: Path, dst: Path) -> Action:
    action = Action(
        type=ActionType.MOVE,
        label=f"Move {src.name}",
        targets=[str(src)],
        before_state={"path": str(src)},
        after_state={"path": str(dst)},
        status=ActionStatus.PROPOSED,
    )
    return action_store.add(action)


def _make_rename_action(src: Path, dst: Path) -> Action:
    action = Action(
        type=ActionType.RENAME,
        label=f"Rename {src.name}",
        targets=[str(src)],
        before_state={"path": str(src)},
        after_state={"path": str(dst)},
        status=ActionStatus.PROPOSED,
    )
    return action_store.add(action)


def _make_delete_action(src: Path) -> Action:
    action = Action(
        type=ActionType.DELETE,
        label=f"Delete {src.name}",
        targets=[str(src)],
        before_state={"path": str(src)},
        after_state={},
        status=ActionStatus.PROPOSED,
    )
    return action_store.add(action)


def _cleanup(*paths):
    for p in paths:
        try:
            if isinstance(p, Path):
                p.unlink(missing_ok=True)
            else:
                Path(p).unlink(missing_ok=True)
        except Exception:
            pass


# ── Part 1: MOVE ──────────────────────────────────────────────────────────────

def test_move():
    print("\n" + "=" * 60)
    print("PART 1 -- MOVE action")
    print("=" * 60)

    clear_roots()
    action_store.clear()

    src = _make_file(b"move me", ".tmp")
    dst_dir = Path(tempfile.mkdtemp(prefix="wisp_exec_dst_"))
    dst = dst_dir / "moved.tmp"

    action = _make_move_action(src, dst)
    aid = action.id

    try:
        result = execute_action(aid)

        check("T1: execute returns Action", isinstance(result, Action))
        check("T2: status is APPLIED", result.status == ActionStatus.APPLIED)
        check("T3: source file no longer exists", not src.exists(),
              f"src={src} still exists")
        check("T4: dest file now exists", dst.exists(),
              f"dst={dst} missing")
        check("T5: dest file has correct content",
              dst.read_bytes() == b"move me")

        # Store reflects APPLIED
        stored = action_store.get(aid)
        check("T6: store shows APPLIED", stored.status == ActionStatus.APPLIED)
    finally:
        _cleanup(src, dst)
        shutil.rmtree(dst_dir, ignore_errors=True)
        action_store.clear()


# ── Part 2: MOVE creates parent directories ───────────────────────────────────

def test_move_creates_parents():
    print("\n" + "=" * 60)
    print("PART 2 -- MOVE creates parent directories")
    print("=" * 60)

    clear_roots()
    action_store.clear()

    src = _make_file(b"nested move")
    base = Path(tempfile.mkdtemp(prefix="wisp_exec_nest_"))
    dst = base / "a" / "b" / "c" / "nested.txt"

    action = _make_move_action(src, dst)
    try:
        execute_action(action.id)
        check("T7: nested dest directories created", dst.exists(),
              f"dst={dst} missing")
    finally:
        _cleanup(src)
        shutil.rmtree(base, ignore_errors=True)
        action_store.clear()


# ── Part 3: RENAME ────────────────────────────────────────────────────────────

def test_rename():
    print("\n" + "=" * 60)
    print("PART 3 -- RENAME action")
    print("=" * 60)

    clear_roots()
    action_store.clear()

    src = _make_file(b"rename me", ".txt")
    dst = src.parent / "renamed_file.txt"

    action = _make_rename_action(src, dst)
    try:
        result = execute_action(action.id)
        check("T8: RENAME status is APPLIED", result.status == ActionStatus.APPLIED)
        check("T9: original file gone", not src.exists())
        check("T10: renamed file exists", dst.exists())
        check("T11: content preserved", dst.read_bytes() == b"rename me")
    finally:
        _cleanup(src, dst)
        action_store.clear()


# ── Part 4: DELETE ────────────────────────────────────────────────────────────

def test_delete():
    print("\n" + "=" * 60)
    print("PART 4 -- DELETE action")
    print("=" * 60)

    clear_roots()
    action_store.clear()

    src = _make_file(b"delete me", ".tmp")
    action = _make_delete_action(src)

    try:
        result = execute_action(action.id)
        check("T12: DELETE status is APPLIED", result.status == ActionStatus.APPLIED)
        check("T13: file is gone after DELETE", not src.exists())
    finally:
        _cleanup(src)
        action_store.clear()


# ── Part 5: Wrong status guards ───────────────────────────────────────────────

def test_wrong_status_guards():
    print("\n" + "=" * 60)
    print("PART 5 -- Wrong status guards")
    print("=" * 60)

    clear_roots()
    action_store.clear()

    src = _make_file(b"guard test")
    dst_dir = Path(tempfile.mkdtemp(prefix="wisp_guard_"))
    dst = dst_dir / "done.txt"
    action = _make_move_action(src, dst)

    # Execute once successfully
    execute_action(action.id)

    # Attempt to execute again (APPLIED -> error)
    try:
        execute_action(action.id)
        check("T14: re-executing APPLIED action raises", False,
              "should have raised ExecutionError")
    except ExecutionError:
        check("T14: re-executing APPLIED action raises ExecutionError", True)

    # Undo it, then try to execute the UNDONE action
    import shutil as _shutil
    _shutil.move(str(dst), str(src))  # manually reverse for test
    action_store.set_status(action.id, ActionStatus.UNDONE)
    try:
        execute_action(action.id)
        check("T15: executing UNDONE action raises", False,
              "should have raised ExecutionError")
    except ExecutionError:
        check("T15: executing UNDONE action raises ExecutionError", True)

    # Missing action_id
    try:
        execute_action("nonexistent_id")
        check("T16: missing action_id raises", False)
    except ExecutionError:
        check("T16: missing action_id raises ExecutionError", True)

    _cleanup(src)
    shutil.rmtree(dst_dir, ignore_errors=True)
    action_store.clear()


# ── Part 6: Root scope guard ──────────────────────────────────────────────────

def test_root_scope_guard():
    print("\n" + "=" * 60)
    print("PART 6 -- Root scope guard")
    print("=" * 60)

    action_store.clear()

    root_dir  = Path(tempfile.mkdtemp(prefix="wisp_root_"))
    other_dir = Path(tempfile.mkdtemp(prefix="wisp_other_"))
    src_inside  = root_dir  / "inside.tmp"
    src_outside = other_dir / "outside.tmp"
    src_inside.write_bytes(b"inside")
    src_outside.write_bytes(b"outside")
    dst_inside  = root_dir  / "moved_inside.tmp"
    dst_outside = other_dir / "moved_outside.tmp"

    try:
        add_root(str(root_dir))

        # File inside root -> allowed
        a = _make_move_action(src_inside, dst_inside)
        result = execute_action(a.id)
        check("T17: file inside root -> execute succeeds",
              result.status == ActionStatus.APPLIED)
        check("T18: file actually moved", dst_inside.exists())

        # File outside root -> blocked
        b = _make_move_action(src_outside, dst_outside)
        try:
            execute_action(b.id)
            check("T19: file outside root -> execute raises", False,
                  "should have raised ExecutionError")
        except ExecutionError as e:
            check("T19: file outside root -> ExecutionError raised", True,
                  str(e))

        # Status stays PROPOSED after scope guard rejection
        stored = action_store.get(b.id)
        check("T20: blocked action stays PROPOSED",
              stored.status == ActionStatus.PROPOSED)
    finally:
        clear_roots()
        _cleanup(src_inside, src_outside, dst_inside, dst_outside)
        shutil.rmtree(root_dir, ignore_errors=True)
        shutil.rmtree(other_dir, ignore_errors=True)
        action_store.clear()


# ── Part 7: Execute + undo full round-trip ────────────────────────────────────

def test_execute_undo_roundtrip():
    print("\n" + "=" * 60)
    print("PART 7 -- Execute + undo round-trip")
    print("=" * 60)

    clear_roots()
    action_store.clear()

    src = _make_file(b"round trip content", ".tmp")
    original_path = str(src)
    q_dir = Path(tempfile.mkdtemp(prefix="wisp_q_"))
    dst = q_dir / src.name

    action = _make_move_action(src, dst)

    try:
        # Execute: file moves to quarantine
        execute_action(action.id)
        check("T21: after execute, src gone", not src.exists())
        check("T22: after execute, dst exists", dst.exists())
        check("T23: status is APPLIED", action_store.get(action.id).status == ActionStatus.APPLIED)

        # Undo: file comes back to original location
        src.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(dst), original_path)
        action_store.set_status(action.id, ActionStatus.UNDONE)

        check("T24: after undo, src restored", Path(original_path).exists())
        check("T25: after undo, dst gone", not dst.exists())
        check("T26: status is UNDONE", action_store.get(action.id).status == ActionStatus.UNDONE)
    finally:
        _cleanup(src)
        shutil.rmtree(q_dir, ignore_errors=True)
        action_store.clear()


# ── Part 8: API apply endpoint ────────────────────────────────────────────────

def test_apply_endpoint():
    print("\n" + "=" * 60)
    print("PART 8 -- POST /actions/{id}/apply endpoint")
    print("=" * 60)

    clear_roots()
    action_store.clear()

    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api.v1.actions import router as actions_router

    app = FastAPI()
    app.include_router(actions_router, prefix="/actions")
    client = TestClient(app, raise_server_exceptions=False)

    src = _make_file(b"endpoint test", ".tmp")
    dst_dir = Path(tempfile.mkdtemp(prefix="wisp_ep_dst_"))
    dst = dst_dir / "applied.tmp"
    action = _make_move_action(src, dst)

    try:
        # Apply via HTTP
        resp = client.post(f"/actions/{action.id}/apply")
        check("T27: POST /apply returns 200", resp.status_code == 200,
              f"got {resp.status_code}: {resp.text[:120]}")
        if resp.status_code == 200:
            body = resp.json()
            check("T28: response status is APPLIED",
                  body.get("status") == "APPLIED", f"got {body.get('status')}")
        check("T29: file was physically moved", dst.exists() and not src.exists())

        # Apply again -> 422
        resp2 = client.post(f"/actions/{action.id}/apply")
        check("T30: re-apply returns 422", resp2.status_code == 422,
              f"got {resp2.status_code}")

        # Unknown id -> 404
        resp3 = client.post("/actions/doesnotexist/apply")
        check("T31: unknown id returns 404", resp3.status_code == 404,
              f"got {resp3.status_code}")
    finally:
        _cleanup(src, dst)
        shutil.rmtree(dst_dir, ignore_errors=True)
        action_store.clear()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    test_move()
    test_move_creates_parents()
    test_rename()
    test_delete()
    test_wrong_status_guards()
    test_root_scope_guard()
    test_execute_undo_roundtrip()
    test_apply_endpoint()

    print("\n" + "=" * 60)
    total = _pass + _fail
    if _fail == 0:
        print(f"  Results: {total}/{total} passed -- all good")
    else:
        print(f"  Results: {_pass}/{total} passed, {_fail} FAILED")
    print("=" * 60)
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()

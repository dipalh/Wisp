"""
Action Engine REST API.

Routes
------
  GET  /api/v1/actions              List all actions (filter by ?status=PROPOSED|APPLIED|UNDONE)
  POST /api/v1/actions              Record a new action
  GET  /api/v1/actions/{id}         Get one action by id
  POST /api/v1/actions/{id}/undo    Undo an action
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException

import services.actions as action_store
from services.actions.executor import ExecutionError, execute_action
from services.actions.models import Action, ActionStatus, ActionType

router = APIRouter()


def _undo_action_filesystem(action: Action) -> tuple[bool, str | None, str | None]:
    if action.type == ActionType.TAG:
        return True, None, None

    src = action.after_state.get("path")
    dst = action.before_state.get("path")
    if not src or not dst:
        return False, "UNDO_MISSING_PATH_STATE", "Action missing path in state"
    if not Path(src).exists():
        return False, "UNDO_SOURCE_MISSING", f"Undo source file missing: {src}"
    try:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dst)
        return True, None, None
    except Exception as exc:
        return False, "UNDO_FAILED", f"Could not reverse action: {exc}"


@router.get("", summary="List actions")
async def list_actions(status: str | None = None):
    """Return all actions, optionally filtered by status (PROPOSED, APPLIED, UNDONE)."""
    filter_status: ActionStatus | None = None
    if status is not None:
        try:
            filter_status = ActionStatus(status.upper())
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Unknown status '{status}'")
    return {"actions": action_store.get_all(filter_status)}


@router.post("", summary="Record an action", response_model=Action)
async def create_action(action: Action):
    """Record a new action (PROPOSED or APPLIED)."""
    return action_store.add(action)


@router.get("/{action_id}", summary="Get one action", response_model=Action)
async def get_action(action_id: str):
    action = action_store.get(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail=f"Action '{action_id}' not found")
    return action


@router.post("/{action_id}/apply", summary="Execute a proposed action", response_model=Action)
async def apply_action(action_id: str):
    """Execute a PROPOSED action, making the file operation real.

    Supported types: MOVE (quarantine/archive), RENAME, DELETE.

    The Root Scope Guard is enforced — the source file must be under a
    registered root (or any path is allowed if no roots are set).

    On success the action transitions PROPOSED -> APPLIED and the file
    has been moved/renamed/deleted.
    """
    try:
        return execute_action(action_id)
    except ExecutionError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": str(exc)},
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Execution failed: {exc}")


@router.post("/{action_id}/undo", summary="Undo an action", response_model=Action)
async def undo_action(action_id: str):
    """
    Undo an action.

    - PROPOSED → mark UNDONE immediately (file was never moved)
    - APPLIED MOVE → move file back from after_state to before_state, then mark UNDONE
    - APPLIED DELETE → move file back from quarantine path to original path
    - Already UNDONE → 409
    """
    action = action_store.get(action_id)
    if action is None:
        raise HTTPException(status_code=404, detail=f"Action '{action_id}' not found")

    if action.status == ActionStatus.UNDONE:
        raise HTTPException(status_code=409, detail="Action is already undone")

    if action.status == ActionStatus.PROPOSED:
        # Nothing was ever executed — just cancel it
        return action_store.set_status(action_id, ActionStatus.UNDONE)

    # APPLIED — need to physically reverse
    ok, code, error = _undo_action_filesystem(action)
    if not ok:
        raise HTTPException(status_code=500, detail={"code": code, "message": error})
    return action_store.set_status(action_id, ActionStatus.UNDONE)


@router.post("/batches", summary="Create an action batch")
async def create_batch(payload: dict):
    action_ids = payload.get("action_ids") or []
    proposal_id = payload.get("proposal_id")
    actor = payload.get("actor", "system")
    try:
        batch = action_store.create_batch(
            action_ids,
            proposal_id=proposal_id,
            actor=actor,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"ok": True, **batch}


@router.post("/batches/{batch_id}/apply", summary="Apply an action batch")
async def apply_batch(batch_id: str):
    batch = action_store.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found")

    details: list[dict] = []
    applied = 0
    failed = 0
    for action_id in batch["action_ids"]:
        try:
            execute_action(action_id)
            details.append({"action_id": action_id, "status": ActionStatus.APPLIED.value})
            applied += 1
        except ExecutionError as exc:
            existing = action_store.get(action_id)
            if existing is not None:
                action_store.set_status(
                    action_id,
                    ActionStatus.FAILED,
                    failure_reason=str(exc),
                )
            details.append(
                {
                    "action_id": action_id,
                    "status": ActionStatus.FAILED.value,
                    "code": exc.code,
                    "message": str(exc),
                }
            )
            failed += 1

    if applied and failed:
        status = ActionStatus.PARTIAL
    elif applied:
        status = ActionStatus.APPLIED
    else:
        status = ActionStatus.FAILED

    action_store.set_batch_status(batch_id, status)
    return {
        "ok": True,
        "batch_id": batch_id,
        "status": status.value,
        "applied": applied,
        "failed": failed,
        "details": details,
    }


@router.post("/batches/{batch_id}/undo", summary="Undo an action batch")
async def undo_batch(batch_id: str):
    batch = action_store.get_batch(batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail=f"Batch '{batch_id}' not found")

    details: list[dict] = []
    undone = 0
    failed = 0
    for action_id in batch["action_ids"]:
        action = action_store.get(action_id)
        if action is None:
            details.append(
                {
                    "action_id": action_id,
                    "status": ActionStatus.FAILED.value,
                    "code": "ACTION_NOT_FOUND",
                    "message": f"Action not found: {action_id}",
                }
            )
            failed += 1
            continue
        if action.status == ActionStatus.UNDONE:
            details.append({"action_id": action_id, "status": ActionStatus.UNDONE.value})
            undone += 1
            continue
        if action.status != ActionStatus.APPLIED:
            details.append(
                {
                    "action_id": action_id,
                    "status": ActionStatus.FAILED.value,
                    "code": "ACTION_NOT_APPLIED",
                    "message": f"Action {action_id} is {action.status.value}, expected APPLIED",
                }
            )
            failed += 1
            continue

        ok, code, error = _undo_action_filesystem(action)
        if not ok:
            action_store.set_status(action_id, ActionStatus.PARTIAL, failure_reason=error)
            details.append(
                {
                    "action_id": action_id,
                    "status": ActionStatus.FAILED.value,
                    "code": code,
                    "message": error,
                }
            )
            failed += 1
            continue

        action_store.set_status(action_id, ActionStatus.UNDONE)
        details.append({"action_id": action_id, "status": ActionStatus.UNDONE.value})
        undone += 1

    if undone and failed:
        status = ActionStatus.PARTIAL
    elif undone:
        status = ActionStatus.UNDONE
    else:
        status = ActionStatus.FAILED

    action_store.set_batch_status(batch_id, status)
    return {
        "ok": True,
        "batch_id": batch_id,
        "status": status.value,
        "undone": undone,
        "failed": failed,
        "details": details,
    }

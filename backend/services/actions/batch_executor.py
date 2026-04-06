from __future__ import annotations

import services.actions as action_store
from services.actions.executor import ExecutionError, execute_action
from services.actions.models import Action, ActionStatus


def undo_action_filesystem(action: Action) -> tuple[bool, str | None, str | None]:
    if action.type.value == "TAG":
        return True, None, None

    src = action.after_state.get("path")
    dst = action.before_state.get("path")
    if not src or not dst:
        return False, "UNDO_MISSING_PATH_STATE", "Action missing path in state"

    from pathlib import Path
    import shutil

    if not Path(src).exists():
        return False, "UNDO_SOURCE_MISSING", f"Undo source file missing: {src}"
    try:
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(src, dst)
        return True, None, None
    except Exception as exc:
        return False, "UNDO_FAILED", f"Could not reverse action: {exc}"


def apply_batch(batch_id: str) -> dict | None:
    batch = action_store.get_batch(batch_id)
    if batch is None:
        return None

    details: list[dict] = []
    applied = 0
    failed = 0
    last_error: str | None = None

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
            last_error = str(exc)

    if applied and failed:
        status = ActionStatus.PARTIAL
    elif applied:
        status = ActionStatus.APPLIED
    else:
        status = ActionStatus.FAILED

    action_store.set_batch_status(batch_id, status, failure_reason=last_error)
    return {
        "ok": True,
        "batch_id": batch_id,
        "status": status.value,
        "applied": applied,
        "failed": failed,
        "details": details,
    }


def undo_batch(batch_id: str) -> dict | None:
    batch = action_store.get_batch(batch_id)
    if batch is None:
        return None

    details: list[dict] = []
    undone = 0
    failed = 0
    last_error: str | None = None

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
            last_error = f"Action not found: {action_id}"
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
            last_error = f"Action {action_id} is {action.status.value}, expected APPLIED"
            continue

        ok, code, error = undo_action_filesystem(action)
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
            last_error = error
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

    action_store.set_batch_status(batch_id, status, failure_reason=last_error)
    return {
        "ok": True,
        "batch_id": batch_id,
        "status": status.value,
        "undone": undone,
        "failed": failed,
        "details": details,
    }

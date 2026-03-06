"""
Action Executor — physically applies a PROPOSED action.

Takes a PROPOSED action from the store, executes the file operation,
and transitions it to APPLIED.  This is the complement to the undo
logic in api/v1/actions.py.

Enforces the Root Scope Guard on the source path of every action so
the executor can never touch files outside registered roots.

Supported action types
----------------------
  MOVE   — shutil.move(before_state["path"], after_state["path"])
  RENAME — Path.rename(after_state["path"])
  DELETE — Path.unlink() (hard delete; undo is NOT supported)

Public API
----------
  execute_action(action_id) -> Action   (raises on error)
"""
from __future__ import annotations

import shutil
from pathlib import Path

import services.actions as action_store
from services.actions.models import Action, ActionStatus, ActionType
from services.roots import is_under_root


class ExecutionError(Exception):
    """Raised when an action cannot be executed."""

    def __init__(self, message: str, *, code: str = "EXECUTION_ERROR", status_code: int = 422):
        super().__init__(message)
        self.code = code
        self.status_code = status_code


def execute_action(action_id: str) -> Action:
    """Execute a PROPOSED action and mark it APPLIED.

    Args:
        action_id: ID of an action in the store with status PROPOSED.

    Returns:
        The updated Action with status == APPLIED.

    Raises:
        ExecutionError: If the action cannot be found, is not PROPOSED,
                        the source path is outside registered roots, or
                        the file operation fails.
    """
    action = action_store.get(action_id)
    if action is None:
        raise ExecutionError(
            f"Action not found: {action_id}",
            code="ACTION_NOT_FOUND",
            status_code=404,
        )

    if action.status == ActionStatus.APPLIED:
        raise ExecutionError(
            f"Action {action_id} is already APPLIED",
            code="ACTION_ALREADY_APPLIED",
        )

    if action.status == ActionStatus.UNDONE:
        raise ExecutionError(
            f"Action {action_id} has been UNDONE and cannot be re-applied",
            code="ACTION_ALREADY_UNDONE",
        )

    src_path = action.before_state.get("path", "")
    if not src_path:
        raise ExecutionError("Action has no source path in before_state", code="ACTION_MISSING_SOURCE")

    # Root scope guard — protects every disk-touching operation
    if not is_under_root(src_path):
        raise ExecutionError(
            f"Source path is not under any registered root: {src_path}",
            code="SOURCE_OUTSIDE_ROOT",
        )

    src = Path(src_path)

    if action.type == ActionType.MOVE:
        dst_path = action.after_state.get("path", "")
        if not dst_path:
            raise ExecutionError(
                "MOVE action has no destination path in after_state",
                code="ACTION_MISSING_DESTINATION",
            )
        if not is_under_root(dst_path):
            raise ExecutionError(
                f"Destination path is not under any registered root: {dst_path}",
                code="DESTINATION_OUTSIDE_ROOT",
            )
        dst = Path(dst_path)
        if dst.exists():
            raise ExecutionError(
                f"DESTINATION_COLLISION: destination already exists: {dst_path}",
                code="DESTINATION_COLLISION",
                status_code=409,
            )
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        except Exception as exc:
            raise ExecutionError(f"MOVE failed: {exc}", code="MOVE_FAILED") from exc

    elif action.type == ActionType.RENAME:
        dst_path = action.after_state.get("path", "")
        if not dst_path:
            raise ExecutionError(
                "RENAME action has no destination path in after_state",
                code="ACTION_MISSING_DESTINATION",
            )
        if not is_under_root(dst_path):
            raise ExecutionError(
                f"Destination path is not under any registered root: {dst_path}",
                code="DESTINATION_OUTSIDE_ROOT",
            )
        dst = Path(dst_path)
        if dst.exists():
            raise ExecutionError(
                f"DESTINATION_COLLISION: destination already exists: {dst_path}",
                code="DESTINATION_COLLISION",
                status_code=409,
            )
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
        except Exception as exc:
            raise ExecutionError(f"RENAME failed: {exc}", code="RENAME_FAILED") from exc

    elif action.type == ActionType.DELETE:
        try:
            src.unlink()
        except FileNotFoundError:
            pass  # already gone — treat as success
        except Exception as exc:
            raise ExecutionError(f"DELETE failed: {exc}", code="DELETE_FAILED") from exc

    else:
        raise ExecutionError(
            f"Action type {action.type} is not directly executable",
            code="ACTION_TYPE_NOT_EXECUTABLE",
        )

    return action_store.set_status(action_id, ActionStatus.APPLIED)

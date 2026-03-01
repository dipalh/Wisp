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
        raise ExecutionError(f"Action not found: {action_id}")

    if action.status == ActionStatus.APPLIED:
        raise ExecutionError(f"Action {action_id} is already APPLIED")

    if action.status == ActionStatus.UNDONE:
        raise ExecutionError(f"Action {action_id} has been UNDONE and cannot be re-applied")

    src_path = action.before_state.get("path", "")
    if not src_path:
        raise ExecutionError("Action has no source path in before_state")

    # Root scope guard — protects every disk-touching operation
    if not is_under_root(src_path):
        raise ExecutionError(
            f"Source path is not under any registered root: {src_path}"
        )

    src = Path(src_path)

    if action.type == ActionType.MOVE:
        dst_path = action.after_state.get("path", "")
        if not dst_path:
            raise ExecutionError("MOVE action has no destination path in after_state")
        dst = Path(dst_path)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dst))
        except Exception as exc:
            raise ExecutionError(f"MOVE failed: {exc}") from exc

    elif action.type == ActionType.RENAME:
        dst_path = action.after_state.get("path", "")
        if not dst_path:
            raise ExecutionError("RENAME action has no destination path in after_state")
        dst = Path(dst_path)
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
        except Exception as exc:
            raise ExecutionError(f"RENAME failed: {exc}") from exc

    elif action.type == ActionType.DELETE:
        try:
            src.unlink()
        except FileNotFoundError:
            pass  # already gone — treat as success
        except Exception as exc:
            raise ExecutionError(f"DELETE failed: {exc}") from exc

    else:
        raise ExecutionError(
            f"Action type {action.type} is not directly executable"
        )

    return action_store.set_status(action_id, ActionStatus.APPLIED)

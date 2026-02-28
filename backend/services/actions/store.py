"""
In-memory action store for the Wisp Action Engine.

Session-scoped — resets when the server restarts.
Thread-safe via a threading.Lock.

Public API
----------
  add(action)              -> Action
  get_all(status=None)     -> list[Action]
  get(id)                  -> Action | None
  set_status(id, status)   -> Action        (raises KeyError if not found)
  clear()                  -> None
"""
from __future__ import annotations

import threading

from services.actions.models import Action, ActionStatus

_lock = threading.Lock()
_actions: list[Action] = []


def add(action: Action) -> Action:
    """Append an action to the store and return it."""
    with _lock:
        _actions.append(action)
    return action


def get_all(status: ActionStatus | None = None) -> list[Action]:
    """Return all actions, optionally filtered by status."""
    with _lock:
        if status is None:
            return list(_actions)
        return [a for a in _actions if a.status == status]


def get(action_id: str) -> Action | None:
    """Return the action with the given id, or None."""
    with _lock:
        for a in _actions:
            if a.id == action_id:
                return a
    return None


def set_status(action_id: str, status: ActionStatus) -> Action:
    """Update an action's status in-place. Raises KeyError if not found."""
    with _lock:
        for a in _actions:
            if a.id == action_id:
                a.status = status
                return a
    raise KeyError(f"Action '{action_id}' not found")


def clear() -> None:
    """Remove all actions (useful for testing)."""
    with _lock:
        _actions.clear()

"""
Root Scope Guard — in-memory root folder registry.

Keeps track of user-selected root directories and enforces that every
path-touching operation stays within those roots.

Public API
----------
  add_root(path)       -> str             (resolved absolute path)
  remove_root(path)    -> bool
  get_roots()          -> list[str]
  clear()              -> None
  is_under_root(path)  -> bool            (True if no roots set OR path is under any root)
"""
from __future__ import annotations

import threading
from pathlib import Path

_lock = threading.Lock()
_roots: set[str] = set()


def add_root(path: str) -> str:
    """Resolve and register *path* as a watched root.  Returns the resolved path."""
    resolved = str(Path(path).resolve())
    with _lock:
        _roots.add(resolved)
    return resolved


def remove_root(path: str) -> bool:
    """Unregister a root.  Returns True if it was present."""
    resolved = str(Path(path).resolve())
    with _lock:
        if resolved in _roots:
            _roots.discard(resolved)
            return True
    return False


def get_roots() -> list[str]:
    """Return a sorted list of all registered roots."""
    with _lock:
        return sorted(_roots)


def clear() -> None:
    """Unregister all roots (useful for tests)."""
    with _lock:
        _roots.clear()


def is_under_root(path: str | Path) -> bool:
    """Return True if *path* is inside any registered root.

    If no roots are registered, every path is allowed (open mode).
    This lets existing code work before the user picks a folder.
    """
    with _lock:
        if not _roots:
            return True
        resolved = Path(path).resolve()
        return any(resolved.is_relative_to(Path(r)) for r in _roots)

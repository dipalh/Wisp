"""
Directory scanner for the Wisp ingestor pipeline.

Walks a directory tree, skipping known noise directories and artifact
files, and returns a flat list of file paths up to a configurable depth.

Exclusion rules
---------------
  Directories:  hidden (.*), dev tooling, lancedb, _files, .lproj
  Files:        hidden (.*), Wisp artifacts, SQLite WAL/SHM, Windows junk
  Size:         files above max_file_size_mb (default 100, env WISP_MAX_FILE_SIZE_MB)
"""
from __future__ import annotations

import os
from pathlib import Path

MAX_DEPTH = 4

_SKIP_DIRS = {
    "__pycache__", "node_modules", ".git", ".venv", "venv", ".tox",
    "dist", "build", ".eggs", ".mypy_cache", ".idea", ".vscode",
    "lancedb",
}

_SKIP_FILES = frozenset({
    ".DS_Store",
    "Thumbs.db",
    "desktop.ini",
    "wisp_jobs.db",
    "wisp_ingest_cache.json",
})

_SKIP_SUFFIXES = frozenset({"-wal", "-shm"})

_DEFAULT_MAX_FILE_SIZE_MB = 100


def _skip_dir(name: str) -> bool:
    low = name.lower()
    return (
        (low.startswith(".") and low not in {".app"})
        or low in _SKIP_DIRS
        or low.endswith("_files")
        or low.endswith(".lproj")
    )


def _skip_dotfiles() -> bool:
    """Check env toggle — default True (skip dotfiles)."""
    return os.environ.get("WISP_SKIP_DOTFILES", "1") != "0"


def _skip_file(name: str) -> bool:
    if name in _SKIP_FILES:
        return True
    if name.startswith(".") and _skip_dotfiles():
        return True
    for suffix in _SKIP_SUFFIXES:
        if name.endswith(suffix):
            return True
    return False


def _max_file_bytes(max_file_size_mb: int | None) -> int:
    if max_file_size_mb is not None:
        return max_file_size_mb * 1024 * 1024
    env_val = os.environ.get("WISP_MAX_FILE_SIZE_MB")
    if env_val is not None:
        try:
            return int(env_val) * 1024 * 1024
        except ValueError:
            pass
    return _DEFAULT_MAX_FILE_SIZE_MB * 1024 * 1024


def collect_files(
    root: Path,
    max_depth: int = MAX_DEPTH,
    max_file_size_mb: int | None = None,
) -> list[Path]:
    """Recursively collect all files under *root*, skipping noise.

    Args:
        root:             Directory to scan.
        max_depth:        Maximum recursion depth (0 = root only).
        max_file_size_mb: Skip files larger than this (MB).  Defaults to
                          env ``WISP_MAX_FILE_SIZE_MB`` or 100.

    Returns:
        Sorted flat list of Path objects for every file found.
    """
    max_bytes = _max_file_bytes(max_file_size_mb)
    files: list[Path] = []

    def _walk(d: Path, depth: int) -> None:
        if depth > max_depth:
            return
        try:
            entries = sorted(d.iterdir())
        except PermissionError:
            return
        for item in entries:
            if item.is_dir():
                if _skip_dir(item.name):
                    continue
                _walk(item, depth + 1)
            elif item.is_file():
                if _skip_file(item.name):
                    continue
                if max_bytes > 0:
                    try:
                        if item.stat().st_size > max_bytes:
                            continue
                    except OSError:
                        continue
                elif max_bytes == 0:
                    try:
                        if item.stat().st_size > 0:
                            continue
                    except OSError:
                        continue
                files.append(item)

    _walk(root, 0)
    return files

"""
Directory scanner for the Wisp ingestor pipeline.

Walks a directory tree, skipping known noise directories, and returns
a flat list of file paths up to a configurable depth.
"""
from __future__ import annotations

from pathlib import Path

MAX_DEPTH = 4

_SKIP_DIRS = {
    "__pycache__", "node_modules", ".git", ".venv", "venv", ".tox",
    "dist", "build", ".eggs", ".mypy_cache", ".idea", ".vscode",
}


def _skip_dir(name: str) -> bool:
    low = name.lower()
    return (
        (low.startswith(".") and low not in {".app"})
        or low in _SKIP_DIRS
        or low.endswith("_files")
        or low.endswith(".lproj")
    )


def collect_files(root: Path, max_depth: int = MAX_DEPTH) -> list[Path]:
    """Recursively collect all files under *root*, skipping noise directories.

    Args:
        root:      Directory to scan.
        max_depth: Maximum recursion depth (0 = root only).

    Returns:
        Sorted flat list of Path objects for every file found.
    """
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
            elif item.is_file() and item.name != ".DS_Store":
                files.append(item)

    _walk(root, 0)
    return files

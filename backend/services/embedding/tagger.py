"""
OS-level file tagging for Wisp.

Adds/reads/removes Finder tags on macOS, and supports a cross-platform
fallback via filesystem xattrs where available.

macOS Finder tags use the extended attribute:
    com.apple.metadata:_kMDItemUserTags

Each tag is a string like "Red\n6" where \n6 is the colour code:
    0=None, 1=Gray, 2=Green, 3=Purple, 4=Blue, 5=Yellow, 6=Orange, 7=Red

Usage:
    from services.embedding.tagger import add_tag, remove_tag, get_tags
    add_tag("/path/to/file.pdf", "Deletable", color="red")
    tags = get_tags("/path/to/file.pdf")
    remove_tag("/path/to/file.pdf", "Deletable")
"""
from __future__ import annotations

import plistlib
import platform
import subprocess
import sys
from pathlib import Path


# ── Colour map (macOS Finder tag colours) ─────────────────────────────────

_COLOUR_CODES: dict[str, int] = {
    "none":   0,
    "gray":   1,  "grey": 1,
    "green":  2,
    "purple": 3,
    "blue":   4,
    "yellow": 5,
    "orange": 6,
    "red":    7,
}

_XATTR_KEY = "com.apple.metadata:_kMDItemUserTags"
_IS_MACOS = platform.system() == "Darwin"


# ── Low-level xattr helpers (macOS-only, uses /usr/bin/xattr) ─────────────

def _read_xattr(path: str, key: str) -> bytes | None:
    """Read a single extended attribute.  Returns None if absent."""
    try:
        result = subprocess.run(
            ["xattr", "-px", key, path],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return None
        # xattr -px outputs hex bytes, reconstruct
        hex_str = result.stdout.replace(" ", "").replace("\n", "")
        return bytes.fromhex(hex_str)
    except Exception:
        return None


def _write_xattr(path: str, key: str, data: bytes) -> bool:
    """Write a single extended attribute.  Returns True on success."""
    try:
        # Write via python's subprocess — xattr -wx expects hex
        hex_str = data.hex()
        result = subprocess.run(
            ["xattr", "-wx", key, hex_str, path],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _delete_xattr(path: str, key: str) -> bool:
    """Remove a single extended attribute."""
    try:
        result = subprocess.run(
            ["xattr", "-d", key, path],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


# ── Tag reading / writing ─────────────────────────────────────────────────

def _parse_tags(raw: bytes) -> list[str]:
    """Parse the plist-encoded tag list.  Returns tag names (without colour suffix)."""
    try:
        tags = plistlib.loads(raw)
        # Each entry is "TagName\n<colour_code>"
        return [t.split("\n")[0] for t in tags if isinstance(t, str)]
    except Exception:
        return []


def _encode_tags(tag_entries: list[str]) -> bytes:
    """Encode a list of "TagName\\nColour" strings to plist bytes."""
    return plistlib.dumps(tag_entries, fmt=plistlib.FMT_BINARY)


def _tag_entry(name: str, color: str = "none") -> str:
    """Build a single tag entry string: 'TagName\\nColourCode'."""
    code = _COLOUR_CODES.get(color.lower(), 0)
    return f"{name}\n{code}"


# ── Public API ────────────────────────────────────────────────────────────

def get_tags(file_path: str | Path) -> list[str]:
    """Read all Finder tags from a file.  Returns tag names (without colours).

    On non-macOS systems, returns an empty list.
    """
    if not _IS_MACOS:
        return []
    raw = _read_xattr(str(file_path), _XATTR_KEY)
    if raw is None:
        return []
    return _parse_tags(raw)


def add_tag(
    file_path: str | Path,
    tag_name: str,
    color: str = "none",
) -> bool:
    """Add a Finder tag to a file.  Preserves existing tags.

    Args:
        file_path: Path to the file.
        tag_name:  Tag name (e.g. "Deletable", "Keep", "Review").
        color:     Finder colour: none, gray, green, purple, blue, yellow, orange, red.

    Returns:
        True if the tag was added / already present.
    """
    if not _IS_MACOS:
        return False

    path_str = str(file_path)
    raw = _read_xattr(path_str, _XATTR_KEY)

    # Parse existing tags
    existing_entries: list[str] = []
    if raw:
        try:
            existing_entries = plistlib.loads(raw)
        except Exception:
            existing_entries = []

    # Check if tag already present
    existing_names = [e.split("\n")[0] for e in existing_entries if isinstance(e, str)]
    if tag_name in existing_names:
        return True  # already tagged

    existing_entries.append(_tag_entry(tag_name, color))
    encoded = _encode_tags(existing_entries)
    return _write_xattr(path_str, _XATTR_KEY, encoded)


def remove_tag(
    file_path: str | Path,
    tag_name: str,
) -> bool:
    """Remove a specific Finder tag from a file.

    Returns True if removed (or was not present).
    """
    if not _IS_MACOS:
        return False

    path_str = str(file_path)
    raw = _read_xattr(path_str, _XATTR_KEY)
    if raw is None:
        return True  # no tags at all

    try:
        entries = plistlib.loads(raw)
    except Exception:
        return False

    filtered = [e for e in entries if not (isinstance(e, str) and e.split("\n")[0] == tag_name)]

    if len(filtered) == len(entries):
        return True  # tag wasn't present

    if not filtered:
        return _delete_xattr(path_str, _XATTR_KEY)

    return _write_xattr(path_str, _XATTR_KEY, _encode_tags(filtered))


def has_tag(file_path: str | Path, tag_name: str) -> bool:
    """Check if a file has a specific Finder tag."""
    return tag_name in get_tags(file_path)


def tag_files(
    file_paths: list[str | Path],
    tag_name: str,
    color: str = "none",
) -> dict[str, bool]:
    """Batch-tag multiple files.  Returns {path: success}."""
    results: dict[str, bool] = {}
    for fp in file_paths:
        results[str(fp)] = add_tag(fp, tag_name, color)
    return results


def untag_files(
    file_paths: list[str | Path],
    tag_name: str,
) -> dict[str, bool]:
    """Batch-remove a tag from multiple files.  Returns {path: success}."""
    results: dict[str, bool] = {}
    for fp in file_paths:
        results[str(fp)] = remove_tag(fp, tag_name)
    return results

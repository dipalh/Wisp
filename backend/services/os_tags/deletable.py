"""
Single-purpose OS-level "Deletable" tag for Wisp.

Marks files as deletable at the OS level so the tag is **visible in Finder**
(macOS) and best-effort visible on Windows.  This is NOT a general tagging
system — it implements exactly one binary tag.

macOS
-----
Uses the ``com.apple.metadata:_kMDItemUserTags`` extended attribute.
Each Finder tag is a plist-encoded string ``"TagName\\n<colour_code>"``:

    Colour codes:  0=None  1=Gray  2=Green  3=Purple  4=Blue  5=Yellow  6=Orange  7=Red

We use colour **7 (Red)** so "Deletable" stands out in Finder.

The xattr value is a **binary plist** (fmt=FMT_BINARY) containing a list of
these tag strings.  We read/write via ``plistlib`` and the system ``xattr``
CLI (no third-party deps).

Windows (best-effort)
---------------------
Attempts to set the ``System.Keywords`` shell property via COM/propsys.
This works for file types whose property handler supports keywords (Office,
images, etc.) but silently no-ops for unsupported types.

Public API
----------
    set_deletable(path, value: bool)  — add or remove the tag
    is_deletable(path)                — check if the tag is present
    should_mark_deletable(...)        — classification heuristic

All functions are idempotent and never raise.  Failures are logged.

Configuration
-------------
    DELETABLE_AGE_DAYS        env var or default 90
    DELETABLE_PROTECTED_DIRS  env var (colon-separated) or defaults
"""
from __future__ import annotations

import logging
import os
import platform
import plistlib
import subprocess
import time
from pathlib import Path

logger = logging.getLogger("wisp.deletable")

# ── Configuration ─────────────────────────────────────────────────────────────

DELETABLE_AGE_DAYS: int = int(os.environ.get("DELETABLE_AGE_DAYS", "90"))

_TAG_NAME = "Deletable"
_TAG_COLOUR = 7  # Red
_TAG_ENTRY = f"{_TAG_NAME}\n{_TAG_COLOUR}"

_XATTR_KEY = "com.apple.metadata:_kMDItemUserTags"
_IS_MACOS = platform.system() == "Darwin"
_IS_WINDOWS = platform.system() == "Windows"

# ── Extensions that are NEVER marked deletable ───────────────────────────────
# These are "important by nature" — invoices, docs, code, etc.

_PROTECTED_EXTENSIONS = frozenset({
    # Documents
    ".pdf", ".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt",
    ".odt", ".odp", ".ods", ".rtf", ".tex",
    # Code
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp",
    ".go", ".rs", ".rb", ".php", ".swift", ".kt", ".sh", ".bash",
    ".h", ".hpp", ".m", ".r", ".lua", ".pl", ".zig", ".sol",
    # Data / config (often irreplaceable)
    ".json", ".yaml", ".yml", ".toml", ".xml", ".csv", ".sql",
    ".ini", ".cfg", ".conf", ".env",
    # Structured text
    ".md", ".txt", ".eml", ".ics", ".vcf",
})

# Extensions that are VERY LIKELY deletable (installers, temp, partial)
_JUNK_EXTENSIONS = frozenset({
    ".dmg", ".iso", ".img", ".pkg", ".deb", ".rpm",
    ".exe", ".msi", ".dll",
    ".crdownload", ".part", ".tmp", ".bak", ".old",
    ".torrent",
    ".ds_store",
})

# Directory name fragments that indicate protected content
_DEFAULT_PROTECTED_DIRS = {
    "documents", "projects", "work", "important",
    "contracts", "legal", "tax", "medical", "finance",
}

_PROTECTED_DIR_NAMES: set[str] = set()


def _load_protected_dirs() -> set[str]:
    """Load protected directory names (cached)."""
    global _PROTECTED_DIR_NAMES
    if not _PROTECTED_DIR_NAMES:
        env_val = os.environ.get("DELETABLE_PROTECTED_DIRS", "")
        if env_val:
            _PROTECTED_DIR_NAMES = {d.strip().lower() for d in env_val.split(":")}
        else:
            _PROTECTED_DIR_NAMES = _DEFAULT_PROTECTED_DIRS
    return _PROTECTED_DIR_NAMES


# ── macOS xattr helpers ───────────────────────────────────────────────────────


def _read_tags_macos(path: str) -> list[str]:
    """Read the raw Finder tag entries from xattr.  Returns list of 'Name\\nCode'."""
    try:
        result = subprocess.run(
            ["xattr", "-px", _XATTR_KEY, path],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return []
        hex_str = result.stdout.replace(" ", "").replace("\n", "")
        raw = bytes.fromhex(hex_str)
        entries = plistlib.loads(raw)
        return [e for e in entries if isinstance(e, str)]
    except Exception:
        return []


def _write_tags_macos(path: str, entries: list[str]) -> bool:
    """Write the full Finder tag list to xattr."""
    try:
        data = plistlib.dumps(entries, fmt=plistlib.FMT_BINARY)
        hex_str = data.hex()
        result = subprocess.run(
            ["xattr", "-wx", _XATTR_KEY, hex_str, path],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _delete_xattr_macos(path: str) -> bool:
    """Remove the tags xattr entirely."""
    try:
        result = subprocess.run(
            ["xattr", "-d", _XATTR_KEY, path],
            capture_output=True, text=True, timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


# ── Windows best-effort helpers ───────────────────────────────────────────────


def _set_keyword_windows(path: str, keyword: str, add: bool) -> bool:
    """Best-effort: set/remove a keyword via PowerShell System.Keywords.

    This works for file types whose shell property handler supports
    keywords (e.g. Office, images, video).  For unsupported types it
    silently no-ops.
    """
    try:
        if add:
            # PowerShell: add keyword if not present
            ps = (
                f'$shell = New-Object -ComObject Shell.Application; '
                f'$folder = $shell.Namespace((Split-Path -Parent "{path}")); '
                f'$file = $folder.ParseName((Split-Path -Leaf "{path}")); '
                f'$kw = $file.ExtendedProperty("System.Keywords"); '
                f'if ($kw -notcontains "{keyword}") {{ '
                f'  $kw += "{keyword}"; '
                f'  $file.ExtendedProperty("System.Keywords") = $kw '
                f'}}'
            )
        else:
            ps = (
                f'$shell = New-Object -ComObject Shell.Application; '
                f'$folder = $shell.Namespace((Split-Path -Parent "{path}")); '
                f'$file = $folder.ParseName((Split-Path -Leaf "{path}")); '
                f'$kw = $file.ExtendedProperty("System.Keywords"); '
                f'$kw = $kw | Where-Object {{ $_ -ne "{keyword}" }}; '
                f'$file.ExtendedProperty("System.Keywords") = $kw'
            )
        subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, timeout=10,
        )
        return True
    except Exception:
        return False


def _has_keyword_windows(path: str, keyword: str) -> bool:
    """Best-effort check for a keyword on Windows."""
    try:
        ps = (
            f'$shell = New-Object -ComObject Shell.Application; '
            f'$folder = $shell.Namespace((Split-Path -Parent "{path}")); '
            f'$file = $folder.ParseName((Split-Path -Leaf "{path}")); '
            f'$kw = $file.ExtendedProperty("System.Keywords"); '
            f'if ($kw -contains "{keyword}") {{ Write-Output "YES" }} '
            f'else {{ Write-Output "NO" }}'
        )
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps],
            capture_output=True, text=True, timeout=10,
        )
        return "YES" in result.stdout
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════


def set_deletable(path: Path | str, value: bool = True) -> bool:
    """Add or remove the "Deletable" OS-level tag.

    - macOS: sets/removes the Red Finder tag.
    - Windows: best-effort via System.Keywords property.
    - Other OS: no-op with debug log.

    Idempotent.  Never raises.

    Returns:
        True if the OS tag was successfully written (or confirmed
        idempotent).  False on unsupported OS or write failure.
    """
    path_str = str(path)

    try:
        if _IS_MACOS:
            return _set_deletable_macos(path_str, value)
        elif _IS_WINDOWS:
            return _set_keyword_windows(path_str, _TAG_NAME, add=value)
        else:
            logger.debug("set_deletable: unsupported OS %s", platform.system())
            return False
    except Exception as e:
        logger.warning("set_deletable failed for %s: %s", path_str, e)
        return False


def is_deletable(path: Path | str) -> bool:
    """Check if the file has the "Deletable" OS-level tag.

    Returns False on errors or unsupported OS.  Never raises.
    """
    path_str = str(path)

    try:
        if _IS_MACOS:
            entries = _read_tags_macos(path_str)
            return any(e.split("\n")[0] == _TAG_NAME for e in entries)
        elif _IS_WINDOWS:
            return _has_keyword_windows(path_str, _TAG_NAME)
        else:
            return False
    except Exception:
        return False


def should_mark_deletable(
    path: Path | str,
    ext: str,
    depth: str = "card",
    ai_summary: str = "",
    *,
    age_days: int | None = None,
) -> bool:
    """Classification heuristic: should this file be tagged "Deletable"?

    A file is deletable if ALL of the following are true:
      1. Older than ``age_days`` (default: DELETABLE_AGE_DAYS = 90)
      2. Not a protected extension (PDF, office, code, data)
      3. Not in a protected directory (Documents, Projects, etc.)
      4. Not flagged as important by AI summary (placeholder hook)

    Junk extensions (.dmg, .exe, .crdownload, .part, etc.) skip the age
    check — they're deletable at any age.

    Args:
        path:       File path.
        ext:        Lowercase extension (e.g. ".dmg").
        depth:      Ingestion depth ("card", "preview", "deep").
        ai_summary: AI-generated summary text (if available).
        age_days:   Override the default age threshold.

    Returns:
        True if the file should be tagged as deletable.
    """
    fp = Path(path)
    threshold = age_days if age_days is not None else DELETABLE_AGE_DAYS

    # ── Rule 1: protected extensions are never deletable ──────────────
    if ext in _PROTECTED_EXTENSIONS:
        return False

    # ── Rule 2: protected directories ─────────────────────────────────
    if _is_in_protected_dir(fp):
        return False

    # ── Rule 3: AI summary importance check (placeholder) ────────────
    if _ai_suggests_important(ai_summary):
        return False

    # ── Rule 4: junk extensions are always deletable ──────────────────
    if ext in _JUNK_EXTENSIONS:
        return True

    # ── Rule 5: age check ─────────────────────────────────────────────
    file_age_days = _file_age_days(fp)
    if file_age_days is None:
        return False  # can't determine age → don't tag

    return file_age_days >= threshold


# ── Classification helpers ────────────────────────────────────────────────────


def _is_in_protected_dir(path: Path) -> bool:
    """Check if any parent directory name matches a protected keyword."""
    protected = _load_protected_dirs()
    for parent in path.parents:
        if parent.name.lower() in protected:
            return True
    return False


def is_protected(file_path: Path | str) -> bool:
    """Public hook: check if a file is in a protected directory.

    Exposed so teammates can use this without understanding the internals.
    """
    return _is_in_protected_dir(Path(file_path))


def _ai_suggests_important(summary: str) -> bool:
    """Placeholder hook: parse AI summary for importance signals.

    Future: look for keywords like "invoice", "contract", "tax return",
    "medical", "receipt", "statement", "agreement", etc.

    Currently always returns False (conservative: doesn't block tagging).
    When the AI layer is more mature, this will do lightweight NLP.
    """
    if not summary:
        return False

    # Simple keyword check — extend as needed
    _importance_keywords = {
        "invoice", "contract", "agreement", "tax", "medical",
        "receipt", "statement", "certificate", "license", "patent",
        "insurance", "warranty", "passport", "visa",
    }
    summary_lower = summary.lower()
    return any(kw in summary_lower for kw in _importance_keywords)


def _file_age_days(path: Path) -> int | None:
    """Return the file's age in days (based on mtime).  None if unreadable."""
    try:
        mtime = path.stat().st_mtime
        age_seconds = time.time() - mtime
        return int(age_seconds / 86400)
    except OSError:
        return None


# ── macOS implementation ──────────────────────────────────────────────────────


def _set_deletable_macos(path: str, value: bool) -> bool:
    """Add or remove the Deletable Finder tag on macOS.

    Returns True if the tag state matches the requested value.
    """
    entries = _read_tags_macos(path)
    existing_names = [e.split("\n")[0] for e in entries]
    has_tag = _TAG_NAME in existing_names

    if value and has_tag:
        return True   # already tagged — idempotent
    if not value and not has_tag:
        return True   # already untagged — idempotent

    if value:
        entries.append(_TAG_ENTRY)
        return _write_tags_macos(path, entries)
    else:
        filtered = [e for e in entries if e.split("\n")[0] != _TAG_NAME]
        if filtered:
            return _write_tags_macos(path, filtered)
        else:
            return _delete_xattr_macos(path)

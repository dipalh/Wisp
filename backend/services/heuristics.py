"""
Heuristics Engine — lightweight inline file scorer.

Scores a file from 0.0 (clean) to 1.0 (definite junk) based purely
on filesystem metadata: extension, name patterns, size, and age.
No AI calls; no disk reads beyond os.stat().

The score is intentionally conservative so legitimate files are not
accidentally flagged.  Signals stack additively and cap at 1.0.

Public API
----------
  score_file(path)  -> dict

Return dict keys
----------------
  path               str    — absolute path
  name               str    — filename
  ext                str    — lowercase extension
  size               int    — bytes
  age_days           int    — days since last modification
  junk_score         float  — 0.0 – 1.0
  reasons            list[str]
  recommended_action str    — "delete" | "review" | "keep"
"""
from __future__ import annotations

import re
import time
from pathlib import Path

# ── Junk extension sets ───────────────────────────────────────────────────────

# High-confidence junk: temporary / cache / installer artefacts
_JUNK_EXTENSIONS = frozenset({
    ".tmp", ".temp", ".bak", ".old", ".orig",
    ".crdownload", ".part", ".partial",
    ".pyc", ".pyo",
    ".log",           # score but don't auto-delete; often still useful
    ".thumbs",
})

# Windows / macOS system clutter kept as filenames (no extension)
_JUNK_FILENAMES = frozenset({
    "thumbs.db", "desktop.ini", ".ds_store",
    "hiberfil.sys", "pagefile.sys", "swapfile.sys",
})

# ── Name-pattern signals ─────────────────────────────────────────────────────

_JUNK_NAME_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"^copy of\s+", re.I),             "copy-of prefix"),
    (re.compile(r"\(\d+\)\s*$"),                   "duplicate suffix (N)"),
    (re.compile(r"\bcopy\s*\(\d+\)", re.I),        "copy (N) pattern"),
    (re.compile(r"^untitled(\s*\d+)?$", re.I),     "untitled file"),
    (re.compile(r"^\~\$"),                         "Office temp (~$)"),
    (re.compile(r"^\.#"),                          "Emacs lock file (.#)"),
    (re.compile(r"_backup\b", re.I),               "backup suffix"),
    (re.compile(r"\btemp\b", re.I),                "temp in name"),
    (re.compile(r"\bduplicate\b", re.I),           "duplicate in name"),
    (re.compile(r"\btest\s*copy\b", re.I),         "test copy"),
]

# ── Age / size thresholds ────────────────────────────────────────────────────

_OLD_DAYS = 730    # 2 years → mild age signal
_SCORE_JUNK_EXT    = 0.50
_SCORE_JUNK_NAME   = 0.35
_SCORE_EMPTY       = 0.30
_SCORE_OLD         = 0.15
_THRESHOLD_DELETE  = 0.65
_THRESHOLD_REVIEW  = 0.35


# ── Public API ───────────────────────────────────────────────────────────────


def score_file(path: str | Path) -> dict:
    """Score a single file from filesystem metadata alone.

    Returns a dict with junk_score, reasons, recommended_action, and
    basic file metadata (path, name, ext, size, age_days).

    Never raises — if stat() fails the file gets junk_score=0.0.
    """
    path = Path(path)
    name = path.name
    ext  = path.suffix.lower()
    name_lower = name.lower()

    try:
        stat     = path.stat()
        size     = stat.st_size
        age_days = int((time.time() - stat.st_mtime) / 86400)
    except OSError:
        return {
            "path": str(path), "name": name, "ext": ext,
            "size": 0, "age_days": 0,
            "junk_score": 0.0, "reasons": ["stat failed"],
            "recommended_action": "keep",
        }

    score   = 0.0
    reasons: list[str] = []

    # ── Signal 1: junk extension ──────────────────────────────────────────────
    if ext in _JUNK_EXTENSIONS:
        score += _SCORE_JUNK_EXT
        reasons.append(f"junk extension ({ext})")

    # ── Signal 2: junk filename (no-ext system files) ─────────────────────────
    if name_lower in _JUNK_FILENAMES:
        score += _SCORE_JUNK_EXT
        reasons.append(f"system junk filename ({name})")

    # ── Signal 3: junk name pattern ───────────────────────────────────────────
    stem = path.stem
    for pattern, label in _JUNK_NAME_PATTERNS:
        if pattern.search(stem) or pattern.search(name):
            score += _SCORE_JUNK_NAME
            reasons.append(label)
            break  # one pattern hit is enough

    # ── Signal 4: empty file ──────────────────────────────────────────────────
    if size == 0:
        score += _SCORE_EMPTY
        reasons.append("empty file (0 bytes)")

    # ── Signal 5: old file ────────────────────────────────────────────────────
    if age_days > _OLD_DAYS:
        score += _SCORE_OLD
        reasons.append(f"not modified in {age_days} days")

    score = round(min(1.0, score), 2)

    if score >= _THRESHOLD_DELETE:
        action = "delete"
    elif score >= _THRESHOLD_REVIEW:
        action = "review"
    else:
        action = "keep"

    return {
        "path":               str(path),
        "name":               name,
        "ext":                ext,
        "size":               size,
        "age_days":           age_days,
        "junk_score":         score,
        "reasons":            reasons,
        "recommended_action": action,
    }

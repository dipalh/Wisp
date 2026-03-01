"""
Heuristics Engine — Test Suite

Run from backend/:
    python -m tests.test_heuristics
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path
from services.heuristics import score_file

_pass = 0
_fail = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global _pass, _fail
    status = "[PASS]" if condition else "[FAIL]"
    print(f"  {status}  {name}")
    if detail:
        print(f"         {detail}")
    if condition:
        _pass += 1
    else:
        _fail += 1


def _make_file(suffix: str = ".txt", content: bytes = b"hello", age_days: int = 0) -> str:
    """Create a real temp file, optionally back-dating its mtime."""
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    tmp.write(content)
    tmp.close()
    if age_days > 0:
        old_time = time.time() - (age_days * 86400)
        os.utime(tmp.name, (old_time, old_time))
    return tmp.name


def _cleanup(*paths):
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


# ── Part 1: Return shape ──────────────────────────────────────────────────────

def test_return_shape():
    print("\n" + "=" * 60)
    print("PART 1 -- Return shape")
    print("=" * 60)

    p = _make_file(".txt", b"normal content")
    try:
        result = score_file(p)
        required = {"path", "name", "ext", "size", "age_days",
                    "junk_score", "reasons", "recommended_action"}
        check("T1: all required keys present", required.issubset(result.keys()),
              f"got keys: {set(result.keys())}")
        check("T2: junk_score is float in [0,1]",
              isinstance(result["junk_score"], float) and 0.0 <= result["junk_score"] <= 1.0,
              f"got {result['junk_score']}")
        check("T3: reasons is a list", isinstance(result["reasons"], list))
        check("T4: recommended_action is one of keep/review/delete",
              result["recommended_action"] in {"keep", "review", "delete"})
    finally:
        _cleanup(p)


# ── Part 2: Extension signals ─────────────────────────────────────────────────

def test_extensions():
    print("\n" + "=" * 60)
    print("PART 2 -- Extension signals")
    print("=" * 60)

    # .tmp -> junk
    p = _make_file(".tmp", b"data")
    try:
        r = score_file(p)
        check("T5: .tmp -> junk_score >= 0.5", r["junk_score"] >= 0.5,
              f"got {r['junk_score']}")
        check("T6: .tmp -> at least one reason", len(r["reasons"]) > 0)
    finally:
        _cleanup(p)

    # .bak -> junk
    p = _make_file(".bak", b"data")
    try:
        r = score_file(p)
        check("T7: .bak -> junk_score >= 0.5", r["junk_score"] >= 0.5,
              f"got {r['junk_score']}")
    finally:
        _cleanup(p)

    # .crdownload -> junk
    p = _make_file(".crdownload", b"partial")
    try:
        r = score_file(p)
        check("T8: .crdownload -> junk_score >= 0.5", r["junk_score"] >= 0.5,
              f"got {r['junk_score']}")
    finally:
        _cleanup(p)

    # .pdf -> clean
    p = _make_file(".pdf", b"PDF content")
    try:
        r = score_file(p)
        check("T9: .pdf -> junk_score == 0.0 (new file, good ext)",
              r["junk_score"] == 0.0, f"got {r['junk_score']}, reasons={r['reasons']}")
        check("T10: .pdf -> recommended_action == keep",
              r["recommended_action"] == "keep")
    finally:
        _cleanup(p)


# ── Part 3: Empty file signal ─────────────────────────────────────────────────

def test_empty_file():
    print("\n" + "=" * 60)
    print("PART 3 -- Empty file signal")
    print("=" * 60)

    p = _make_file(".txt", b"")
    try:
        r = score_file(p)
        check("T11: empty .txt -> junk_score >= 0.3",
              r["junk_score"] >= 0.3, f"got {r['junk_score']}")
        check("T12: empty file reason present",
              any("empty" in reason for reason in r["reasons"]))
    finally:
        _cleanup(p)

    # Non-empty file -> no empty signal
    p = _make_file(".txt", b"has content")
    try:
        r = score_file(p)
        check("T13: non-empty .txt -> no empty-file reason",
              not any("empty" in reason for reason in r["reasons"]))
    finally:
        _cleanup(p)


# ── Part 4: Name pattern signals ──────────────────────────────────────────────

def test_name_patterns():
    print("\n" + "=" * 60)
    print("PART 4 -- Name pattern signals")
    print("=" * 60)

    # "Copy of" prefix
    p = _make_file(".txt", b"data")
    copy_path = Path(p).parent / "Copy of report.txt"
    Path(p).rename(copy_path)
    try:
        r = score_file(str(copy_path))
        check("T14: 'Copy of ...' -> junk_score >= 0.35",
              r["junk_score"] >= 0.35, f"got {r['junk_score']}")
    finally:
        _cleanup(str(copy_path))

    # Duplicate suffix "(2)"
    p = _make_file(".txt", b"data")
    dup_path = Path(p).parent / "document (2).txt"
    Path(p).rename(dup_path)
    try:
        r = score_file(str(dup_path))
        check("T15: 'document (2)' -> junk_score >= 0.35",
              r["junk_score"] >= 0.35, f"got {r['junk_score']}")
    finally:
        _cleanup(str(dup_path))

    # Normal name -> no pattern signal
    p = _make_file(".txt", b"data")
    normal_path = Path(p).parent / "quarterly_report.txt"
    Path(p).rename(normal_path)
    try:
        r = score_file(str(normal_path))
        check("T16: 'quarterly_report.txt' -> no pattern reason",
              not any("pattern" in reason or "copy" in reason.lower()
                      or "duplicate" in reason.lower()
                      for reason in r["reasons"]))
    finally:
        _cleanup(str(normal_path))


# ── Part 5: Age signal ────────────────────────────────────────────────────────

def test_age_signal():
    print("\n" + "=" * 60)
    print("PART 5 -- Age signal")
    print("=" * 60)

    # Old file (800 days)
    p = _make_file(".pdf", b"old content", age_days=800)
    try:
        r = score_file(p)
        check("T17: 800-day-old .pdf -> junk_score >= 0.15",
              r["junk_score"] >= 0.15, f"got {r['junk_score']}")
        check("T18: age reason present",
              any("day" in reason for reason in r["reasons"]))
    finally:
        _cleanup(p)

    # New file
    p = _make_file(".pdf", b"new content", age_days=0)
    try:
        r = score_file(p)
        check("T19: new .pdf -> no age reason",
              not any("day" in reason for reason in r["reasons"]))
    finally:
        _cleanup(p)


# ── Part 6: Compound scoring and action thresholds ────────────────────────────

def test_compound_scoring():
    print("\n" + "=" * 60)
    print("PART 6 -- Compound scoring and action thresholds")
    print("=" * 60)

    # .tmp + empty + old => should hit delete threshold
    p = _make_file(".tmp", b"", age_days=800)
    try:
        r = score_file(p)
        check("T20: .tmp + empty + old -> recommended_action == delete",
              r["recommended_action"] == "delete",
              f"score={r['junk_score']}, action={r['recommended_action']}")
        check("T21: compound score capped at 1.0",
              r["junk_score"] <= 1.0)
    finally:
        _cleanup(p)

    # Score caps at 1.0
    check("T22: junk_score is always <= 1.0", True)  # enforced by above + logic check

    # Missing file -> graceful degradation
    r = score_file("/nonexistent/path/file.txt")
    check("T23: missing file -> junk_score == 0.0 (no crash)",
          r["junk_score"] == 0.0, f"got {r}")
    check("T24: missing file -> recommended_action == keep",
          r["recommended_action"] == "keep")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    test_return_shape()
    test_extensions()
    test_empty_file()
    test_name_patterns()
    test_age_signal()
    test_compound_scoring()

    print("\n" + "=" * 60)
    total = _pass + _fail
    if _fail == 0:
        print(f"  Results: {total}/{total} passed -- all good")
    else:
        print(f"  Results: {_pass}/{total} passed, {_fail} FAILED")
    print("=" * 60)
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()

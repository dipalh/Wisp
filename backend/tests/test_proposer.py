"""
Proposer — Test Suite

Run from backend/:
    python -m tests.test_proposer
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dataclasses import dataclass, field
from pathlib import Path

import services.actions as action_store
from services.actions.models import ActionStatus, ActionType
from services.proposer import PROPOSAL_THRESHOLD, propose_from_hits, quarantine_dir_for
from services.roots import add_root, clear as clear_roots

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


# ── Minimal SearchHit stand-in (avoids importing the full pipeline) ───────────

@dataclass
class FakeHit:
    file_path: str
    file_id:   str    = "fake_id"
    depth:     str    = "deep"
    text:      str    = ""
    score:     float  = 0.9
    ext:       str    = ""
    chunk_id:  str    = ""
    chunk_index: int  = 0
    tags:      list   = field(default_factory=list)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_junk_file(suffix: str = ".tmp", age_days: int = 0) -> str:
    """Create a real temp file that the heuristics engine will flag."""
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.write(b"junk content")
    f.close()
    if age_days:
        old = time.time() - age_days * 86400
        os.utime(f.name, (old, old))
    return f.name


def _make_clean_file(suffix: str = ".pdf") -> str:
    """Create a real temp file that the heuristics engine will not flag."""
    f = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    f.write(b"important document content")
    f.close()
    return f.name


def _cleanup(*paths):
    for p in paths:
        try:
            Path(p).unlink(missing_ok=True)
        except Exception:
            pass
    # Also clean up quarantine dirs created during tests
    for p in paths:
        q = Path(p).parent / ".wisp_quarantine"
        if q.exists():
            shutil.rmtree(q, ignore_errors=True)


# ── Part 1: Junk file generates a proposal ───────────────────────────────────

def test_junk_file_gets_proposal():
    print("\n" + "=" * 60)
    print("PART 1 -- Junk file gets proposal")
    print("=" * 60)

    clear_roots()
    action_store.clear()

    junk = _make_junk_file(".tmp")
    try:
        hits = [FakeHit(file_path=junk, file_id="f1")]
        proposals = propose_from_hits(hits)

        check("T1: one proposal returned", len(proposals) == 1,
              f"got {len(proposals)}")
        p = proposals[0]
        check("T2: proposal has action_id", bool(p.get("action_id")))
        check("T3: proposal file_path matches",
              p["file_path"] == junk, f"got {p['file_path']}")
        check("T4: proposal action_type is MOVE", p["action_type"] == "MOVE")
        check("T5: destination is in .wisp_quarantine dir",
              ".wisp_quarantine" in p["destination"])
        check("T6: junk_score >= threshold",
              p["junk_score"] >= PROPOSAL_THRESHOLD,
              f"got {p['junk_score']}")
        check("T7: reasons list not empty", len(p["reasons"]) > 0)
        check("T8: label is a non-empty string", bool(p.get("label")))

        # Action was recorded in store as PROPOSED
        recorded = action_store.get(p["action_id"])
        check("T9: action recorded in store", recorded is not None)
        check("T10: action status is PROPOSED",
              recorded and recorded.status == ActionStatus.PROPOSED)
        check("T11: action type is MOVE",
              recorded and recorded.type == ActionType.MOVE)
        check("T12: before_state has original path",
              recorded and recorded.before_state.get("path") == junk)
    finally:
        _cleanup(junk)
        action_store.clear()


# ── Part 2: Clean file generates no proposal ─────────────────────────────────

def test_clean_file_no_proposal():
    print("\n" + "=" * 60)
    print("PART 2 -- Clean file skipped")
    print("=" * 60)

    clear_roots()
    action_store.clear()

    clean = _make_clean_file(".pdf")
    try:
        hits = [FakeHit(file_path=clean, file_id="f2")]
        proposals = propose_from_hits(hits)
        check("T13: clean .pdf -> 0 proposals", len(proposals) == 0,
              f"got {len(proposals)}")
        check("T14: no action recorded in store", action_store.get_all() == [])
    finally:
        _cleanup(clean)
        action_store.clear()


# ── Part 3: Deduplication ─────────────────────────────────────────────────────

def test_deduplication():
    print("\n" + "=" * 60)
    print("PART 3 -- Duplicate hits deduplicated")
    print("=" * 60)

    clear_roots()
    action_store.clear()

    junk = _make_junk_file(".tmp")
    try:
        # Same file_path appears in three hits (different chunks)
        hits = [
            FakeHit(file_path=junk, file_id="f1", chunk_index=0),
            FakeHit(file_path=junk, file_id="f1", chunk_index=1),
            FakeHit(file_path=junk, file_id="f1", chunk_index=2),
        ]
        proposals = propose_from_hits(hits)
        check("T15: 3 hits same file -> exactly 1 proposal",
              len(proposals) == 1, f"got {len(proposals)}")
        check("T16: exactly 1 action in store",
              len(action_store.get_all()) == 1)
    finally:
        _cleanup(junk)
        action_store.clear()


# ── Part 4: Missing / non-existent files ─────────────────────────────────────

def test_missing_file_skipped():
    print("\n" + "=" * 60)
    print("PART 4 -- Non-existent file is skipped")
    print("=" * 60)

    action_store.clear()

    hits = [FakeHit(file_path="/nonexistent/path/temp.tmp", file_id="f3")]
    proposals = propose_from_hits(hits)
    check("T17: missing file -> 0 proposals (no crash)", len(proposals) == 0,
          f"got {len(proposals)}")

    hits_empty_path = [FakeHit(file_path="", file_id="f4")]
    proposals = propose_from_hits(hits_empty_path)
    check("T18: empty file_path -> 0 proposals", len(proposals) == 0)

    action_store.clear()


# ── Part 5: Multiple files, mixed junk/clean ──────────────────────────────────

def test_mixed_files():
    print("\n" + "=" * 60)
    print("PART 5 -- Mixed junk and clean files")
    print("=" * 60)

    clear_roots()
    action_store.clear()

    junk1 = _make_junk_file(".tmp")
    junk2 = _make_junk_file(".bak")
    clean = _make_clean_file(".py")
    try:
        hits = [
            FakeHit(file_path=junk1, file_id="j1"),
            FakeHit(file_path=clean, file_id="c1"),
            FakeHit(file_path=junk2, file_id="j2"),
        ]
        proposals = propose_from_hits(hits)
        check("T19: 2 junk + 1 clean -> 2 proposals",
              len(proposals) == 2, f"got {len(proposals)}")
        paths = {p["file_path"] for p in proposals}
        check("T20: both junk files in proposals",
              junk1 in paths and junk2 in paths,
              f"got {paths}")
        check("T21: clean file not in proposals", clean not in paths)
    finally:
        _cleanup(junk1, junk2, clean)
        action_store.clear()


# ── Part 6: Quarantine directory derivation ───────────────────────────────────

def test_quarantine_dir():
    print("\n" + "=" * 60)
    print("PART 6 -- Quarantine directory derivation")
    print("=" * 60)

    root_dir = tempfile.mkdtemp(prefix="wisp_qtest_root_")
    other_dir = tempfile.mkdtemp(prefix="wisp_qtest_other_")
    try:
        # No roots: quarantine is sibling .wisp_quarantine
        clear_roots()
        file_in_other = Path(other_dir) / "notes.txt"
        q = quarantine_dir_for(file_in_other)
        check("T22: no roots -> quarantine is sibling .wisp_quarantine",
              q == Path(other_dir) / ".wisp_quarantine",
              f"got {q}")

        # With registered root: file under root -> root/.wisp_quarantine
        add_root(root_dir)
        file_in_root = Path(root_dir) / "subdir" / "temp.tmp"
        q = quarantine_dir_for(file_in_root)
        check("T23: registered root -> quarantine in root/.wisp_quarantine",
              q == Path(root_dir) / ".wisp_quarantine",
              f"got {q}")

        # File outside registered root -> falls back to sibling
        file_outside = Path(other_dir) / "other.tmp"
        q = quarantine_dir_for(file_outside)
        check("T24: file outside root -> sibling .wisp_quarantine",
              q == Path(other_dir) / ".wisp_quarantine",
              f"got {q}")
    finally:
        clear_roots()
        shutil.rmtree(root_dir, ignore_errors=True)
        shutil.rmtree(other_dir, ignore_errors=True)


# ── Part 7: Old+junk compound scoring still generates proposal ────────────────

def test_compound_score_proposal():
    print("\n" + "=" * 60)
    print("PART 7 -- Compound junk score produces proposal")
    print("=" * 60)

    action_store.clear()

    # .bak + 800 days old -> well above threshold
    old_bak = _make_junk_file(".bak", age_days=800)
    try:
        hits = [FakeHit(file_path=old_bak, file_id="f5")]
        proposals = propose_from_hits(hits)
        check("T25: old .bak -> 1 proposal", len(proposals) == 1,
              f"got {len(proposals)}")
        if proposals:
            check("T26: junk_score > 0.6 for old .bak",
                  proposals[0]["junk_score"] > 0.6,
                  f"got {proposals[0]['junk_score']}")
    finally:
        _cleanup(old_bak)
        action_store.clear()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    test_junk_file_gets_proposal()
    test_clean_file_no_proposal()
    test_deduplication()
    test_missing_file_skipped()
    test_mixed_files()
    test_quarantine_dir()
    test_compound_score_proposal()

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

"""
Root Scope Guard — Test Suite

Run from backend/:
    python -m tests.test_roots
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path
from services.roots import add_root, remove_root, get_roots, clear, is_under_root

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


# ── Setup: two real temp directories ─────────────────────────────────────────

def _make_temp_dirs():
    root_a = tempfile.mkdtemp(prefix="wisp_root_a_")
    root_b = tempfile.mkdtemp(prefix="wisp_root_b_")
    sub = Path(root_a) / "subdir"
    sub.mkdir()
    outside = tempfile.mkdtemp(prefix="wisp_outside_")
    return root_a, root_b, str(sub), outside


# ── Part 1: Registry CRUD ─────────────────────────────────────────────────────

def test_registry():
    print("\n" + "=" * 60)
    print("PART 1 — Registry CRUD")
    print("=" * 60)

    clear()
    check("T1: starts empty", get_roots() == [], f"got {get_roots()}")

    root_a, root_b, sub, outside = _make_temp_dirs()

    resolved_a = add_root(root_a)
    check("T2: add_root returns resolved path", resolved_a == str(Path(root_a).resolve()))
    check("T3: get_roots lists the added root", resolved_a in get_roots())

    add_root(root_b)
    check("T4: two roots registered", len(get_roots()) == 2, f"got {get_roots()}")

    removed = remove_root(root_b)
    check("T5: remove_root returns True when present", removed)
    check("T6: root_b gone after remove", str(Path(root_b).resolve()) not in get_roots())

    removed_again = remove_root(root_b)
    check("T7: remove_root returns False when absent", not removed_again)

    clear()
    check("T8: clear empties the registry", get_roots() == [])


# ── Part 2: is_under_root scope guard ────────────────────────────────────────

def test_scope_guard():
    print("\n" + "=" * 60)
    print("PART 2 — Scope guard (is_under_root)")
    print("=" * 60)

    clear()

    # No roots registered → open mode, everything allowed
    root_a, root_b, sub, outside = _make_temp_dirs()
    check("T9: no roots -> any path allowed", is_under_root(outside))
    check("T10: no roots -> subdir allowed", is_under_root(sub))

    add_root(root_a)

    # Direct root itself
    check("T11: root dir itself is under root", is_under_root(root_a))

    # Subdir under root_a
    check("T12: subdir under root_a is allowed", is_under_root(sub))

    # File inside root_a
    test_file = Path(root_a) / "notes.txt"
    test_file.write_text("hello")
    check("T13: file inside root_a is allowed", is_under_root(str(test_file)))

    # Path outside any root
    check("T14: outside dir is blocked", not is_under_root(outside))

    # root_b not registered
    check("T15: unregistered root_b is blocked", not is_under_root(root_b))

    add_root(root_b)
    check("T16: after adding root_b, root_b is allowed", is_under_root(root_b))

    clear()
    # After clear: open mode again
    check("T17: after clear -> open mode restored", is_under_root(outside))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    test_registry()
    test_scope_guard()

    print("\n" + "=" * 60)
    total = _pass + _fail
    if _fail == 0:
        print(f"  Results: {total}/{total} passed — all good")
    else:
        print(f"  Results: {_pass}/{total} passed, {_fail} FAILED")
    print("=" * 60)
    sys.exit(1 if _fail else 0)


if __name__ == "__main__":
    main()

"""
Deletable Tag — Test Harness
=============================

Run from ``backend/``:

    python -m tests.test_deletable

Tests:
  1. Tagging: set, check, remove, idempotency
  2. Classification heuristic: age, extensions, protected dirs
  3. Finder visibility (macOS only — manual spot-check)
"""
from __future__ import annotations

import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path
from services.os_tags.deletable import (
    set_deletable,
    is_deletable,
    should_mark_deletable,
    is_protected,
    _file_age_days,
    _TAG_NAME,
    _JUNK_EXTENSIONS,
    _PROTECTED_EXTENSIONS,
)

# ── Test helpers ──────────────────────────────────────────────────────────────

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


# ── T1–T5: OS-level tagging ──────────────────────────────────────────────────

def test_tagging() -> None:
    print("\n" + "=" * 60)
    print("PART 1 — OS-level tagging (set / check / remove)")
    print("=" * 60)

    # Create a temp file
    with tempfile.NamedTemporaryFile(suffix=".txt", delete=False, dir="/tmp") as f:
        f.write(b"test content for deletable tagging")
        path = f.name

    try:
        # T1: initially not tagged
        check("T1: file starts untagged", not is_deletable(path))

        # T2: set deletable
        set_deletable(path, True)
        check("T2: set_deletable(True) → is_deletable() == True", is_deletable(path))

        # T3: idempotent — set again
        set_deletable(path, True)
        check("T3: double set_deletable(True) → still True", is_deletable(path))

        # T4: remove
        set_deletable(path, False)
        check("T4: set_deletable(False) → is_deletable() == False", not is_deletable(path))

        # T5: idempotent — remove again
        set_deletable(path, False)
        check("T5: double set_deletable(False) → still False", not is_deletable(path))

    finally:
        os.unlink(path)


# ── T6–T12: Classification heuristic ─────────────────────────────────────────

def test_classification() -> None:
    print("\n" + "=" * 60)
    print("PART 2 — Classification heuristic")
    print("=" * 60)

    # T6: junk extension → always deletable (even if brand new)
    with tempfile.NamedTemporaryFile(suffix=".dmg", delete=False, dir="/tmp") as f:
        f.write(b"fake dmg")
        dmg_path = f.name
    try:
        result = should_mark_deletable(dmg_path, ".dmg", depth="card")
        check("T6: .dmg → deletable (junk ext)", result, f"got {result}")
    finally:
        os.unlink(dmg_path)

    # T7: protected extension → never deletable
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False, dir="/tmp") as f:
        f.write(b"fake pdf")
        pdf_path = f.name
    try:
        result = should_mark_deletable(pdf_path, ".pdf", depth="deep")
        check("T7: .pdf → NOT deletable (protected ext)", not result, f"got {result}")
    finally:
        os.unlink(pdf_path)

    # T8: .py → never deletable
    result = should_mark_deletable("/tmp/test.py", ".py")
    check("T8: .py → NOT deletable (protected code ext)", not result)

    # T9: old image → deletable
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False, dir="/tmp") as f:
        f.write(b"fake png")
        png_path = f.name
    try:
        # Modify mtime to 100 days ago
        old_time = time.time() - (100 * 86400)
        os.utime(png_path, (old_time, old_time))
        result = should_mark_deletable(png_path, ".png", depth="preview", age_days=90)
        check("T9: old .png (100d) → deletable", result, f"age={_file_age_days(Path(png_path))}d")
    finally:
        os.unlink(png_path)

    # T10: new image → NOT deletable
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False, dir="/tmp") as f:
        f.write(b"fake png")
        new_png = f.name
    try:
        result = should_mark_deletable(new_png, ".png", depth="preview", age_days=90)
        check("T10: new .png (0d) → NOT deletable", not result, f"age={_file_age_days(Path(new_png))}d")
    finally:
        os.unlink(new_png)

    # T11: AI summary with importance keyword → not deletable
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False, dir="/tmp") as f:
        f.write(b"fake zip")
        zip_path = f.name
    try:
        old_time = time.time() - (200 * 86400)
        os.utime(zip_path, (old_time, old_time))
        result = should_mark_deletable(
            zip_path, ".zip", ai_summary="This contains the signed contract agreement"
        )
        check("T11: old .zip with 'contract' AI summary → NOT deletable", not result)
    finally:
        os.unlink(zip_path)

    # T12: is_protected helper
    check(
        "T12: is_protected('/Users/x/Documents/invoice.zip') == True",
        is_protected(Path("/Users/x/Documents/invoice.zip")),
    )
    check(
        "T12b: is_protected('/tmp/junk.dmg') == False",
        not is_protected(Path("/tmp/junk.dmg")),
    )


# ── T13: Finder visibility spot-check (macOS only) ───────────────────────────

def test_finder_visibility() -> None:
    import platform
    if platform.system() != "Darwin":
        print("\n  [SKIP] Finder visibility test — not on macOS")
        return

    print("\n" + "=" * 60)
    print("PART 3 — Finder visibility (macOS spot-check)")
    print("=" * 60)

    path: str | None = None
    candidate_dirs = [str(Path.home() / "Desktop"), tempfile.gettempdir()]
    last_error: Exception | None = None

    for candidate_dir in candidate_dirs:
        try:
            os.makedirs(candidate_dir, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                suffix=".txt",
                delete=False,
                dir=candidate_dir,
                prefix="wisp_deletable_test_",
            ) as f:
                f.write(b"This file should have a RED 'Deletable' tag in Finder.")
                path = f.name
            break
        except (PermissionError, FileNotFoundError, OSError) as exc:
            last_error = exc
            continue

    if path is None:
        raise RuntimeError(
            f"Could not create Finder visibility test file in {candidate_dirs}"
        ) from last_error

    set_deletable(path, True)
    tagged = is_deletable(path)
    check(
        f"T13: Desktop file tagged → check Finder: {Path(path).name}",
        tagged,
        "Open Finder → Desktop → right-click → Get Info → look for 'Deletable' (Red)",
    )

    # Cleanup — remove tag but leave file for manual inspection
    # (comment out the next line if you want to see it in Finder)
    set_deletable(path, False)
    os.unlink(path)
    print("  (cleaned up test file)")


def test_finder_visibility_handles_desktop_permission_error(monkeypatch, tmp_path) -> None:
    import platform
    if platform.system() != "Darwin":
        return

    desktop_dir = str(tmp_path / "Desktop")
    original_named_temporary_file = tempfile.NamedTemporaryFile
    creation_dirs: list[str] = []

    def _fake_named_temporary_file(*args, **kwargs):
        target_dir = kwargs.get("dir")
        creation_dirs.append(target_dir)
        if target_dir == desktop_dir:
            raise PermissionError("Operation not permitted")
        return original_named_temporary_file(*args, **kwargs)

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", _fake_named_temporary_file)
    monkeypatch.setattr(sys.modules[__name__], "set_deletable", lambda *a, **k: True)
    monkeypatch.setattr(sys.modules[__name__], "is_deletable", lambda *a, **k: True)
    monkeypatch.setattr(Path, "home", lambda: tmp_path)

    test_finder_visibility()
    assert creation_dirs[0] == desktop_dir
    assert len(creation_dirs) >= 2


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    test_tagging()
    test_classification()
    test_finder_visibility()

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

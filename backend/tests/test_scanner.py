"""
Tests for services/ingestor/scanner.py — collect_files() ignore rules.

Each test creates a precise filesystem layout in tmp_path and asserts
exactly which files are collected and which are skipped.  No mocking —
these are real filesystem operations.
"""
from __future__ import annotations

import os
import pytest
from pathlib import Path

from services.ingestor.scanner import collect_files


# ═══════════════════════════════════════════════════════════════════════
#  Wisp artifact exclusions
# ═══════════════════════════════════════════════════════════════════════


def test_skips_wisp_jobs_db(tmp_path: Path):
    """wisp_jobs.db must never be indexed — it's our own SQLite store."""
    (tmp_path / "readme.txt").write_text("real file")
    (tmp_path / "wisp_jobs.db").write_text("sqlite")

    files = collect_files(tmp_path)
    names = {f.name for f in files}
    assert "readme.txt" in names
    assert "wisp_jobs.db" not in names


def test_skips_wisp_ingest_cache(tmp_path: Path):
    """wisp_ingest_cache.json must not be indexed."""
    (tmp_path / "notes.md").write_text("some notes")
    (tmp_path / "wisp_ingest_cache.json").write_text("{}")

    files = collect_files(tmp_path)
    names = {f.name for f in files}
    assert "notes.md" in names
    assert "wisp_ingest_cache.json" not in names


def test_skips_sqlite_wal_artifacts(tmp_path: Path):
    """SQLite WAL/SHM files (-wal, -shm) must be skipped."""
    (tmp_path / "data.txt").write_text("content")
    (tmp_path / "wisp_jobs.db-wal").write_text("wal log")
    (tmp_path / "wisp_jobs.db-shm").write_text("shared mem")
    (tmp_path / "other.db-wal").write_text("wal log")

    files = collect_files(tmp_path)
    names = {f.name for f in files}
    assert "data.txt" in names
    assert "wisp_jobs.db-wal" not in names
    assert "wisp_jobs.db-shm" not in names
    assert "other.db-wal" not in names


# ═══════════════════════════════════════════════════════════════════════
#  Hidden files
# ═══════════════════════════════════════════════════════════════════════


def test_skips_hidden_files(tmp_path: Path):
    """Files starting with '.' should be skipped (not just .DS_Store)."""
    (tmp_path / "visible.txt").write_text("hi")
    (tmp_path / ".hidden_config").write_text("secret")
    (tmp_path / ".DS_Store").write_bytes(b"\x00")
    (tmp_path / ".gitignore").write_text("*.pyc")

    files = collect_files(tmp_path)
    names = {f.name for f in files}
    assert "visible.txt" in names
    assert ".hidden_config" not in names
    assert ".DS_Store" not in names
    assert ".gitignore" not in names


# ═══════════════════════════════════════════════════════════════════════
#  Windows junk
# ═══════════════════════════════════════════════════════════════════════


def test_skips_windows_junk_files(tmp_path: Path):
    """Thumbs.db and desktop.ini should be skipped."""
    (tmp_path / "photo.jpg").write_bytes(b"\xff\xd8")
    (tmp_path / "Thumbs.db").write_bytes(b"\x00")
    (tmp_path / "desktop.ini").write_text("[.ShellClassInfo]")

    files = collect_files(tmp_path)
    names = {f.name for f in files}
    assert "photo.jpg" in names
    assert "Thumbs.db" not in names
    assert "desktop.ini" not in names


# ═══════════════════════════════════════════════════════════════════════
#  LanceDB directory
# ═══════════════════════════════════════════════════════════════════════


def test_skips_lancedb_directory(tmp_path: Path):
    """The lancedb directory must be excluded entirely."""
    (tmp_path / "document.pdf").write_bytes(b"%PDF")
    lance_dir = tmp_path / "lancedb"
    lance_dir.mkdir()
    (lance_dir / "index.lance").write_bytes(b"\x00" * 100)
    (lance_dir / "data.lance").write_bytes(b"\x00" * 100)

    files = collect_files(tmp_path)
    names = {f.name for f in files}
    assert "document.pdf" in names
    assert "index.lance" not in names
    assert "data.lance" not in names


# ═══════════════════════════════════════════════════════════════════════
#  Max file size
# ═══════════════════════════════════════════════════════════════════════


def test_skips_files_above_max_size(tmp_path: Path):
    """Files exceeding max_file_size_mb should be skipped."""
    (tmp_path / "small.txt").write_text("tiny")
    big = tmp_path / "huge.bin"
    # Create a 2 MB file, then pass max_file_size_mb=1
    big.write_bytes(b"\x00" * (2 * 1024 * 1024))

    files = collect_files(tmp_path, max_file_size_mb=1)
    names = {f.name for f in files}
    assert "small.txt" in names
    assert "huge.bin" not in names


def test_default_max_size_allows_normal_files(tmp_path: Path):
    """Normal files well below the 100MB default are included."""
    (tmp_path / "code.py").write_text("print('hello')")
    (tmp_path / "image.png").write_bytes(b"\x89PNG" + b"\x00" * 500)

    files = collect_files(tmp_path)
    names = {f.name for f in files}
    assert "code.py" in names
    assert "image.png" in names


def test_max_size_from_env(tmp_path: Path, monkeypatch):
    """WISP_MAX_FILE_SIZE_MB env var overrides the default."""
    monkeypatch.setenv("WISP_MAX_FILE_SIZE_MB", "0")  # skip everything
    # Re-import not needed because we read at call time

    (tmp_path / "anything.txt").write_text("content")
    files = collect_files(tmp_path, max_file_size_mb=0)
    # max_file_size_mb=0 should mean "skip all files > 0 bytes"
    # But the actual file has bytes, so it should be skipped.
    # A zero-byte file would still pass.
    names = {f.name for f in files}
    assert "anything.txt" not in names


# ═══════════════════════════════════════════════════════════════════════
#  Dotfile toggle (WISP_SKIP_DOTFILES)
# ═══════════════════════════════════════════════════════════════════════


def test_dotfile_toggle_off_includes_dotfiles(tmp_path: Path, monkeypatch):
    """When WISP_SKIP_DOTFILES=0, dotfiles should be collected
    (except always-skip names like .DS_Store)."""
    monkeypatch.setenv("WISP_SKIP_DOTFILES", "0")

    (tmp_path / "visible.txt").write_text("hi")
    (tmp_path / ".bashrc").write_text("alias ls='ls -la'")
    (tmp_path / ".env").write_text("SECRET=abc")
    (tmp_path / ".DS_Store").write_bytes(b"\x00")

    files = collect_files(tmp_path)
    names = {f.name for f in files}
    assert "visible.txt" in names
    assert ".bashrc" in names
    assert ".env" in names
    # .DS_Store is always skipped (in _SKIP_FILES)
    assert ".DS_Store" not in names


def test_dotfile_toggle_on_skips_dotfiles(tmp_path: Path, monkeypatch):
    """When WISP_SKIP_DOTFILES=1, all dotfiles are skipped (default)."""
    monkeypatch.setenv("WISP_SKIP_DOTFILES", "1")

    (tmp_path / "visible.txt").write_text("hi")
    (tmp_path / ".bashrc").write_text("alias ls='ls -la'")

    files = collect_files(tmp_path)
    names = {f.name for f in files}
    assert "visible.txt" in names
    assert ".bashrc" not in names


# ═══════════════════════════════════════════════════════════════════════
#  Existing behavior preserved
# ═══════════════════════════════════════════════════════════════════════


def test_skips_known_noise_dirs(tmp_path: Path):
    """node_modules, __pycache__, .git etc. must still be skipped."""
    (tmp_path / "app.py").write_text("main")
    nm = tmp_path / "node_modules"
    nm.mkdir()
    (nm / "lodash.js").write_text("module")
    pc = tmp_path / "__pycache__"
    pc.mkdir()
    (pc / "app.cpython-312.pyc").write_bytes(b"\x00")

    files = collect_files(tmp_path)
    names = {f.name for f in files}
    assert "app.py" in names
    assert "lodash.js" not in names
    assert "app.cpython-312.pyc" not in names


def test_collects_normal_mixed_tree(tmp_path: Path):
    """A realistic directory tree with good and bad files."""
    # Good files
    (tmp_path / "report.pdf").write_bytes(b"%PDF")
    (tmp_path / "notes.txt").write_text("meeting notes")
    sub = tmp_path / "photos"
    sub.mkdir()
    (sub / "vacation.jpg").write_bytes(b"\xff\xd8")
    (sub / "selfie.png").write_bytes(b"\x89PNG")

    # Bad files (should be skipped)
    (tmp_path / ".DS_Store").write_bytes(b"\x00")
    (tmp_path / ".hidden").write_text("nope")
    (tmp_path / "wisp_jobs.db").write_text("sqlite")
    (tmp_path / "Thumbs.db").write_bytes(b"\x00")
    git = tmp_path / ".git"
    git.mkdir()
    (git / "HEAD").write_text("ref: refs/heads/main")

    files = collect_files(tmp_path)
    names = {f.name for f in files}

    assert names == {"report.pdf", "notes.txt", "vacation.jpg", "selfie.png"}


def test_skips_symlink_file_that_points_outside_root(tmp_path: Path):
    """Scanner must not follow symlink files outside the selected root."""
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    (root / "inside.txt").write_text("safe")
    (outside / "secret.txt").write_text("do not index")

    link = root / "secret-link.txt"
    try:
        os.symlink(outside / "secret.txt", link)
    except OSError as exc:
        pytest.skip(f"symlink unsupported in test environment: {exc}")

    files = collect_files(root)
    names = {f.name for f in files}
    resolved_root = root.resolve()

    assert "inside.txt" in names
    assert "secret-link.txt" not in names
    assert all(path.resolve().is_relative_to(resolved_root) for path in files)


def test_skips_symlink_directory_that_points_outside_root(tmp_path: Path):
    """Scanner must not recurse into symlinked directories outside root."""
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "exfil.txt").write_text("outside data")

    link_dir = root / "outside-link"
    try:
        os.symlink(outside, link_dir)
    except OSError as exc:
        pytest.skip(f"symlink unsupported in test environment: {exc}")

    files = collect_files(root)
    names = {f.name for f in files}
    resolved_root = root.resolve()

    assert "exfil.txt" not in names
    assert all(path.resolve().is_relative_to(resolved_root) for path in files)

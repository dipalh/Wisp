"""
End-to-end test: scan a directory → ingest → suggest new directory structure.

Usage (from backend/):
    python -m tests.test_suggest [directory]

Defaults to C:\\Users\\mikep\\OneDrive\\Documents if no argument is given.
Uses a temporary LanceDB so the real index is never touched.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

# ── path setup ────────────────────────────────────────────────────────────────
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
_BACKEND = Path(__file__).parent.parent  # backend/
sys.path.insert(0, str(_BACKEND))

from dotenv import load_dotenv
load_dotenv(_BACKEND / ".env", override=False)


# ── progress callback ─────────────────────────────────────────────────────────

_total_files = 0


def _print_progress(idx: int, total: int, display: str, engine_result: str) -> None:
    global _total_files
    _total_files = total
    short = display if len(display) <= 60 else "…" + display[-57:]
    print(f"  [{idx:>3}/{total}] {short}  → {engine_result}")


# ── pretty-print suggestions ──────────────────────────────────────────────────

def print_suggestions(suggestions) -> None:
    print("\n" + "═" * 70)
    print("  DIRECTORY STRUCTURE SUGGESTIONS")
    print("═" * 70)

    for i, p in enumerate(suggestions.proposals, 1):
        print(f"\n{'─' * 70}")
        print(f"  Proposal {i}: {p.name}")
        print(f"{'─' * 70}")
        print(f"  Rationale: {p.rationale}\n")

        print("  Folder tree:")
        for folder in p.folder_tree:
            print(f"    📁 {folder}")

        print(f"\n  File mappings ({len(p.mappings)} files):")
        for m in p.mappings:
            orig = m.original_path if len(m.original_path) <= 45 else "…" + m.original_path[-42:]
            print(f"    {orig}")
            print(f"      → {m.suggested_path}")

    print(f"\n{'═' * 70}")
    print(f"  RECOMMENDATION")
    print(f"{'═' * 70}")
    print(f"  {suggestions.recommendation}")
    print(f"{'═' * 70}\n")


# ── main ──────────────────────────────────────────────────────────────────────

async def main() -> None:
    from services.ingestor import MEMORY_CAP_MB, collect_files, ingest_directory

    target_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"C:\Users\mikep\OneDrive\Documents")

    if not target_dir.is_dir():
        print(f"ERROR: not a directory: {target_dir}")
        sys.exit(1)

    print(f"Target directory : {target_dir}")
    print(f"Memory cap       : {MEMORY_CAP_MB} MB (larger files use filename inference)")

    # ── 1. scan ───────────────────────────────────────────────────────────────
    print("\nScanning …")
    t0 = time.time()
    files = collect_files(target_dir)
    print(f"Found {len(files)} files in {time.time() - t0:.1f}s")

    if not files:
        print("No files found — nothing to index.")
        return

    # ── 2. temp LanceDB ───────────────────────────────────────────────────────
    tmp_db = tempfile.mkdtemp(prefix="wisp_suggest_test_")
    print(f"Temp LanceDB     : {tmp_db}")

    try:
        from services.embedding import store
        store.init(tmp_db)

        # ── 3. ingest ─────────────────────────────────────────────────────────
        print(f"\nIngesting {len(files)} files …\n")
        t1 = time.time()
        await ingest_directory(target_dir, progress_cb=_print_progress)
        print(f"\nIngestion done in {time.time() - t1:.1f}s  "
              f"({store.collection_count()} chunks stored)")

        # ── 4. suggest ────────────────────────────────────────────────────────
        print("\nAsking Gemini for directory suggestions …")
        from services.organizer.suggester import suggest_directories
        t2 = time.time()
        suggestions = await suggest_directories()
        print(f"Got response in {time.time() - t2:.1f}s")

        # ── 5. print ──────────────────────────────────────────────────────────
        print_suggestions(suggestions)

        # ── also dump raw JSON ────────────────────────────────────────────────
        out_path = _BACKEND / "suggest_output.json"
        out_path.write_text(
            json.dumps(suggestions.model_dump(), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"Full JSON saved to: {out_path}")

    finally:
        store.teardown()
        shutil.rmtree(tmp_db, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())

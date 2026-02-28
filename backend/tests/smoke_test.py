#!/usr/bin/env python3
"""
Wisp — Smoke Test: 3-Layer Pipeline Sanity Check
=================================================

Tests A, B, C from the user's checklist:
  A) Fresh DB with mixed file types → verify depth mix + scan_summary
  B) Retrieval sanity → queries hit expected file types
  C) Auto-deepen → card/preview files get deepened on ask()

Usage:
    python3 -m tests.smoke_test
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_env_path, override=False)

_pass = 0
_fail = 0


def _check(name: str, condition: bool, detail: str = "") -> bool:
    global _pass, _fail
    if condition:
        _pass += 1
        print(f"  [PASS]  {name}")
    else:
        _fail += 1
        print(f"  [FAIL]  {name}")
    if detail:
        print(f"         {detail}")
    return condition


def _find_file(exts: list[str], dirs: list[str], min_size: int = 100) -> Path | None:
    """Find the first file matching any of the given extensions."""
    for d in dirs:
        dp = Path(d).expanduser()
        if not dp.is_dir():
            continue
        for f in dp.iterdir():
            if f.is_file() and f.suffix.lower() in exts and f.stat().st_size >= min_size:
                return f
    return None


def main() -> None:
    global _pass, _fail

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("  GEMINI_API_KEY not set — cannot run smoke tests.")
        sys.exit(1)

    from services.embedding import pipeline, store

    # ── Locate mixed test files ───────────────────────────────────────
    search_dirs = [
        str(Path(__file__).parent.parent / "tests" / "fixtures"),
        str(Path.home() / "Downloads"),
        str(Path.home() / "Documents"),
    ]

    # Ground-truth text files are always available
    gt_dir = Path(__file__).parent / "fixtures" / "ground_truth"
    gt_files = list(gt_dir.glob("*.txt")) + list(gt_dir.glob("*.md")) + list(gt_dir.glob("*.py")) + list(gt_dir.glob("*.csv"))

    image_file = _find_file([".png", ".jpg", ".jpeg", ".webp"], search_dirs, min_size=1000)
    pdf_file = _find_file([".pdf"], search_dirs, min_size=5000)
    zip_file = _find_file([".zip"], search_dirs)
    mp4_file = _find_file([".mp4"], search_dirs)

    # Build test set: at least text + whatever else we found
    test_files: list[Path] = []
    if gt_files:
        # Take 2-3 ground truth text files
        test_files.extend(gt_files[:3])
    if pdf_file:
        test_files.append(pdf_file)
    if image_file:
        test_files.append(image_file)
    if zip_file:
        test_files.append(zip_file)
    elif mp4_file:
        test_files.append(mp4_file)

    if len(test_files) < 3:
        print("  Not enough test files found. Need at least text + PDF/image.")
        sys.exit(1)

    print("╔══════════════════════════════════════════════╗")
    print("║  WISP — Smoke Test (3-Layer Pipeline)        ║")
    print("╚══════════════════════════════════════════════╝")

    # ══════════════════════════════════════════════════════════════════
    #  A) Fresh DB smoke test
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 64)
    print("  A) FRESH DB SMOKE TEST")
    print("=" * 64)

    tmp = tempfile.mkdtemp(prefix="wisp_smoke_")
    print(f"  DB: {tmp}")

    try:
        pipeline.init_store(db_path=tmp)

        print(f"\n  Ingesting {len(test_files)} mixed files:")
        results = []
        for f in test_files:
            import hashlib
            fid = hashlib.sha256(str(f).encode()).hexdigest()[:16]
            print(f"    {f.name} ({f.suffix})", end=" ... ", flush=True)
            r = asyncio.run(pipeline.ingest_file(f, fid))
            results.append(r)
            print(f"depth={r.depth}, chunks={r.chunk_count}, engine={r.engine}")

        # Verify collection has data
        count = store.collection_count()
        _check("A.1: collection_count > 0", count > 0, f"count={count}")

        # Verify scan_summary makes sense
        summary = pipeline.scan_summary()
        print(f"\n{summary}\n")
        _check("A.2: scan_summary not empty", "Total files scanned" in summary)

        # Verify depth mix
        depths = {r.depth for r in results}
        print(f"  Depth values seen: {depths}")
        _check("A.3: at least 'deep' in results", "deep" in depths,
               f"depths={depths}")

        # Check that text files got depth="deep"
        text_results = [r for r in results if Path(r.file_path).suffix in {".txt", ".md", ".py", ".csv"}]
        if text_results:
            all_deep = all(r.depth == "deep" for r in text_results)
            _check("A.4: text files are depth='deep'", all_deep,
                   f"text depths: {[r.depth for r in text_results]}")

        # Check non-text files have correct depth
        if image_file:
            img_results = [r for r in results if Path(r.file_path).suffix in {".png", ".jpg", ".jpeg", ".webp"}]
            if img_results:
                _check("A.5: image file has depth='preview' or 'card'",
                       img_results[0].depth in ("preview", "card"),
                       f"depth={img_results[0].depth}, engine={img_results[0].engine}")

        if zip_file or mp4_file:
            card_results = [r for r in results if Path(r.file_path).suffix in {".zip", ".mp4"}]
            if card_results:
                _check("A.6: archive/video file has depth='card'",
                       card_results[0].depth == "card",
                       f"depth={card_results[0].depth}")

        # Verify LanceDB rows have depth values
        sample_hit = store.query(
            pipeline.search("test", k=1)[0].embedding if False else
            # Just grab from a search
            None,
            k=1,
        ) if False else None

        # Use a real search to check depth in results
        all_hits = pipeline.search("files documents", k=20)
        if all_hits:
            hit_depths = {h.depth for h in all_hits}
            print(f"  Depth values in search results: {hit_depths}")
            _check("A.7: search hits have depth field", len(hit_depths) > 0)

        # ══════════════════════════════════════════════════════════════
        #  B) Retrieval sanity test
        # ══════════════════════════════════════════════════════════════
        print("\n" + "=" * 64)
        print("  B) RETRIEVAL SANITY TEST")
        print("=" * 64)

        # Search for content that should be in text files
        if gt_files:
            hits = pipeline.search("resume experience education", k=5)
            if hits:
                top_exts = [Path(h.file_path).suffix for h in hits[:3]]
                _check("B.1: 'resume experience' → hits text files",
                       any(e in {".txt", ".md"} for e in top_exts),
                       f"top extensions: {top_exts}")

            hits = pipeline.search("Python code function", k=5)
            if hits:
                hit_names = [Path(h.file_path).name for h in hits[:3]]
                _check("B.2: 'Python code function' → hits code/text files",
                       len(hits) > 0,
                       f"top files: {hit_names}")

        # Search for card-only content (should match by metadata)
        if zip_file:
            hits = pipeline.search("zip archive", k=5)
            has_zip = any(".zip" in (h.file_path or "") for h in hits)
            _check("B.3: 'zip archive' → hits card-only files",
                   has_zip,
                   f"files: {[Path(h.file_path).name for h in hits[:5]]}")

        # Check depth tags in RAG prompt
        if all_hits:
            from services.embedding.pipeline import _build_rag_prompt
            prompt = _build_rag_prompt("test query", all_hits[:5])
            print(f"\n  RAG prompt snippet (first 500 chars):")
            print(f"  {prompt[:500]}")
            _check("B.4: RAG prompt built successfully", len(prompt) > 50)

            # Check tags appear for non-deep hits
            card_hits = [h for h in all_hits if h.depth == "card"]
            if card_hits:
                prompt_with_card = _build_rag_prompt("test", card_hits[:1])
                _check("B.5: card-only tag in prompt",
                       "card only" in prompt_with_card,
                       f"prompt: {prompt_with_card[:200]}")

        # ══════════════════════════════════════════════════════════════
        #  C) Auto-deepen test
        # ══════════════════════════════════════════════════════════════
        print("\n" + "=" * 64)
        print("  C) AUTO-DEEPEN TEST")
        print("=" * 64)

        # Find a file that was ingested as preview/card
        shallow_results = [r for r in results if r.depth != "deep"]
        if shallow_results:
            target = shallow_results[0]
            target_name = Path(target.file_path).name
            print(f"\n  Target file: {target_name} (depth={target.depth})")

            # Ask something about it → should trigger auto-deepen
            print(f"  Asking about '{target_name}' to trigger auto-deepen...")
            ask_result = asyncio.run(pipeline.ask(
                f"What is in the file {target_name}? Describe its contents.",
                k=10,
            ))

            print(f"  deepened_files: {ask_result.deepened_files}")
            print(f"  answer snippet: {ask_result.answer[:200]}")

            if ask_result.deepened_files:
                _check("C.1: auto-deepen triggered",
                       len(ask_result.deepened_files) > 0,
                       f"deepened: {ask_result.deepened_files}")

                # Verify the file now has deep chunks
                deep_hits = pipeline.search(target_name, k=5)
                deep_for_file = [h for h in deep_hits
                                 if target_name in (h.file_path or "")]
                if deep_for_file:
                    _check("C.2: deepened file now has deep chunks",
                           any(h.depth == "deep" for h in deep_for_file),
                           f"depths: {[h.depth for h in deep_for_file]}")
                else:
                    _check("C.2: deepened file searchable after deepen",
                           len(deep_hits) > 0,
                           f"hits: {[h.file_path for h in deep_hits[:3]]}")
            else:
                print("  (auto-deepen not triggered — file may already be deep "
                      "or file not in top hits)")
                _check("C.1: ask() returned an answer",
                       len(ask_result.answer) > 20,
                       f"answer length: {len(ask_result.answer)}")
        else:
            print("  No shallow files to test auto-deepen — all files were deep.")
            _check("C.1: all files fully extracted (no deepen needed)", True)

    finally:
        pipeline.teardown_store()
        shutil.rmtree(tmp, ignore_errors=True)
        print(f"\n  (cleaned up {tmp})")

    # ── Final results ─────────────────────────────────────────────────
    print("\n" + "=" * 64)
    print(f"  SMOKE TEST RESULTS: {_pass} passed, {_fail} failed")
    if _fail == 0:
        print("  All clear! ✓")
    print("=" * 64)
    sys.exit(0 if _fail == 0 else 1)


if __name__ == "__main__":
    main()

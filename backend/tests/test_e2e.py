"""
Wisp -- End-to-End Flow Integration Test

Exercises all three backend flows against any folder you point at:

  Flow 1  Scan / Index   -- register root, walk files, embed, heuristic score
  Flow 2  Search         -- semantic search to surface relevant files
  Flow 3  Assistant      -- RAG answer + proposals, interactive apply / undo

Usage
-----
  python -m tests.test_e2e --dir C:/path/to/folder
  python -m tests.test_e2e --dir ~/Documents --query "find my Python scripts"
  python -m tests.test_e2e --dir ~/Downloads --dry-run   # preview, no moves

Options
-------
  --dir    <path>   (required) Folder to scan and index.
  --query  <str>    Question to ask the assistant after indexing.
                    Default: "What files in here look like junk or
                             temporary clutter that I should clean up?"
  --dry-run         Show proposals but do not apply any file operations.
  --keep-store      Keep the LanceDB index after the run (default: delete).
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
import textwrap
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Force UTF-8 stdout so box-drawing chars and Gemini responses don't crash
# on Windows consoles that default to cp1252.
if hasattr(sys.stdout, "buffer"):
    import io as _io
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(dotenv_path=_env_path, override=False)

# ── Colour / formatting helpers ───────────────────────────────────────────────

_WIDTH = 70

def _hr(char: str = "-") -> None:
    print(char * _WIDTH)

def _banner(title: str, char: str = "=") -> None:
    print()
    _hr(char)
    print(f"  {title}")
    _hr(char)

def _check(name: str, ok: bool, detail: str = "") -> bool:
    status = "[PASS]" if ok else "[FAIL]"
    print(f"  {status}  {name}")
    if detail:
        for line in detail.splitlines():
            print(f"         {line}")
    return ok

def _require_api_key() -> bool:
    if os.environ.get("GEMINI_API_KEY"):
        return True
    print("\n  [ERROR]  GEMINI_API_KEY is not set.")
    print("           Set it in backend/.env or export it before running.")
    return False


# ── Phase 1: Scan / Index (Flow 1) ───────────────────────────────────────────

async def phase_scan(root: Path) -> list[dict]:
    """Register root, ingest all files, score heuristics. Returns junk candidates."""
    from services.embedding import pipeline
    from services.heuristics import score_file
    from services.ingestor.scanner import collect_files
    from services.roots import add_root

    _banner("PHASE 1 -- Scan / Index  (Flow 1)")

    add_root(str(root))
    print(f"  Root registered: {root}")

    files = collect_files(root)
    print(f"  Files found (after skipping noise dirs): {len(files)}")
    print(f"  (node_modules, .git, __pycache__, etc. excluded)")

    print(f"\n  Ingesting {len(files)} files -- this calls Gemini, may take a minute...")
    _hr()

    errors = 0
    for idx, fp in enumerate(files, 1):
        try:
            await pipeline.ingest_file(fp)
        except Exception as exc:
            errors += 1
            print(f"  [WARN] {fp.name}: {exc}")
        # Simple progress line (overwrite in-place)
        done = idx
        bar_len = 30
        filled = int(bar_len * done / len(files))
        bar = "#" * filled + "-" * (bar_len - filled)
        sys.stdout.write(f"\r  [{bar}] {done}/{len(files)}  errors={errors} ")
        sys.stdout.flush()

    print()  # newline after progress bar
    print()
    print(pipeline.scan_summary())

    # Score all files for junk
    candidates: list[dict] = []
    for fp in files:
        s = score_file(fp)
        if s["junk_score"] >= 0.35:
            s["file_path"] = str(fp)
            candidates.append(s)

    candidates.sort(key=lambda x: x["junk_score"], reverse=True)

    print(f"\n  Heuristic junk candidates ({len(candidates)}):")
    if candidates:
        for c in candidates:
            reasons_str = ", ".join(c["reasons"])
            print(f"    score={c['junk_score']:.2f}  {Path(c['file_path']).name}")
            print(f"           reasons: {reasons_str}")
    else:
        print("    (none -- all files look clean by heuristics)")

    return candidates


# ── Phase 2: Search (Flow 2) ──────────────────────────────────────────────────

def phase_search(query: str) -> None:
    """Quick semantic search to confirm the index is working."""
    from services.embedding import pipeline

    _banner("PHASE 2 -- Search  (Flow 2)")
    print(f"  Query: \"{query[:60]}\"")
    hits = pipeline.search(query, k=5)
    if not hits:
        print("  (no results -- index may be empty)")
        return
    print(f"  Top {len(hits)} hits:")
    for i, h in enumerate(hits, 1):
        label = Path(h.file_path).name if h.file_path else h.file_id
        snippet = h.text[:80].replace("\n", " ")
        print(f"    [{i}] score={h.score:.3f}  depth={h.depth}  {label}")
        print(f"         {snippet}")


# ── Phase 3: Assistant + Proposals (Flow 3) ───────────────────────────────────

async def phase_assistant(query: str) -> list[dict]:
    """Ask the assistant, collect proposals from RAG hits."""
    from services.embedding import pipeline
    from services.proposer import propose_from_hits

    _banner("PHASE 3 -- Assistant / Propose  (Flow 3)")
    print(f"  Query: \"{query[:60]}\"")
    print("  (calling Gemini for RAG answer...)\n")

    result = await pipeline.ask(query, k=15)

    # Print answer wrapped to width
    print("  Answer:")
    _hr()
    for line in result.answer.splitlines():
        for wrapped in textwrap.wrap(line, width=_WIDTH - 4) or [""]:
            print(f"  {wrapped}")
    _hr()

    if result.deepened_files:
        print(f"\n  Auto-deepened {len(result.deepened_files)} file(s) for richer context:")
        for fp in result.deepened_files:
            print(f"    {Path(fp).name}")

    # Generate proposals from hits
    proposals = propose_from_hits(result.hits)
    print(f"\n  Proposals from assistant hits ({len(proposals)}):")
    if proposals:
        for p in proposals:
            print(f"    [{p['action_id'][:8]}]  score={p['junk_score']:.2f}  {Path(p['file_path']).name}")
            print(f"              -> {Path(p['destination']).parent.name}/{Path(p['destination']).name}")
            print(f"              reason: {', '.join(p['reasons'])}")
    else:
        print("    (none -- assistant hits did not trigger proposals)")

    return proposals


# ── Phase 4: Execute proposals (Flow 3) ───────────────────────────────────────

def phase_execute(
    scan_candidates: list[dict],
    assistant_proposals: list[dict],
    dry_run: bool,
) -> None:
    """Merge heuristic + assistant proposals, let user pick, then apply."""
    import services.actions as action_store
    from services.actions.executor import ExecutionError, execute_action
    from services.heuristics import score_file
    from services.proposer import propose_from_hits

    _banner("PHASE 4 -- Execute / Undo  (Flow 3)")

    # Build combined list: assistant proposals + additional heuristic candidates
    # that weren't already proposed.
    proposed_paths = {p["file_path"] for p in assistant_proposals}
    all_proposals = list(assistant_proposals)

    # Heuristic candidates not yet proposed -> create actions now
    for cand in scan_candidates:
        fp_str = cand["file_path"]
        if fp_str in proposed_paths:
            continue
        fp = Path(fp_str)
        if not fp.exists():
            continue
        # Use proposer logic inline for consistent quarantine path
        from services.proposer import quarantine_dir_for
        import time
        from services.actions.models import Action, ActionStatus, ActionType
        q_dir = quarantine_dir_for(fp)
        dest = q_dir / fp.name
        if dest.exists():
            dest = q_dir / f"{fp.stem}_{int(time.time())}{fp.suffix}"
        reasons_str = ", ".join(cand["reasons"])
        label = (
            f"Quarantine {fp.name} "
            f"(junk score: {int(cand['junk_score']*100)}%, {reasons_str})"
        )
        action = Action(
            type=ActionType.MOVE,
            label=label,
            targets=[str(fp)],
            before_state={"path": str(fp)},
            after_state={"path": str(dest)},
            status=ActionStatus.PROPOSED,
        )
        action_store.add(action)
        all_proposals.append({
            "action_id":      action.id,
            "file_path":      str(fp),
            "destination":    str(dest),
            "junk_score":     cand["junk_score"],
            "reasons":        cand["reasons"],
            "recommended_action": cand.get("recommended_action", "review"),
            "label":          label,
            "action_type":    "MOVE",
        })
        proposed_paths.add(fp_str)

    if not all_proposals:
        print("  No proposals to review. The folder looks clean.")
        return

    print(f"  Combined proposals ({len(all_proposals)}):\n")
    for i, p in enumerate(all_proposals, 1):
        name = Path(p["file_path"]).name
        dest_name = Path(p["destination"]).name
        dest_dir  = Path(p["destination"]).parent.name
        print(f"  [{i}] {name}")
        print(f"       Score: {p['junk_score']:.2f}  |  {', '.join(p['reasons'])}")
        print(f"       -> quarantine/{dest_dir}/{dest_name}")
        print()

    if dry_run:
        print("  [DRY-RUN] No files moved (--dry-run flag set).")
        return

    # Interactive selection
    print("  Which proposals do you want to apply?")
    print("  Enter numbers (comma-separated), 'all', or 'none' to skip:")
    print()
    try:
        raw = input("  > ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print("\n  (cancelled)")
        return

    if raw in ("none", "n", "", "q", "quit"):
        print("  Skipped -- no changes made.")
        return

    selected: list[dict]
    if raw == "all":
        selected = all_proposals
    else:
        indices: list[int] = []
        for token in raw.replace(",", " ").split():
            try:
                idx = int(token)
                if 1 <= idx <= len(all_proposals):
                    indices.append(idx - 1)
                else:
                    print(f"  [WARN] Index {idx} out of range, skipped.")
            except ValueError:
                print(f"  [WARN] '{token}' is not a number, skipped.")
        selected = [all_proposals[i] for i in sorted(set(indices))]

    if not selected:
        print("  Nothing selected.")
        return

    print(f"\n  Applying {len(selected)} action(s)...")
    applied, failed = [], []
    for p in selected:
        try:
            execute_action(p["action_id"])
            applied.append(p)
            name = Path(p["file_path"]).name
            dest = Path(p["destination"])
            print(f"    [MOVED]  {name}  ->  {dest.parent.name}/{dest.name}")
        except ExecutionError as exc:
            failed.append((p, str(exc)))
            print(f"    [FAIL]   {Path(p['file_path']).name}: {exc}")

    print()
    _hr("=")
    print(f"  Applied: {len(applied)}   Failed: {len(failed)}")
    _hr("=")

    if applied:
        print("\n  To undo, the actions are in the store.  Run with --undo-all to reverse them.")
        print("  Or call POST /api/v1/actions/{action_id}/undo via the API.")


# ── Main ───────────────────────────────────────────────────────────────────────

def _parse_args() -> tuple[Path, str, bool, bool]:
    args = sys.argv[1:]

    def _get(flag: str, default=None):
        for i, a in enumerate(args):
            if a == flag and i + 1 < len(args):
                return args[i + 1]
        return default

    dry_run    = "--dry-run"    in args
    keep_store = "--keep-store" in args

    dir_arg = _get("--dir")
    if not dir_arg:
        print("Usage: python -m tests.test_e2e --dir <folder> [--query <str>] [--dry-run]")
        sys.exit(1)

    root = Path(dir_arg).expanduser().resolve()
    if not root.is_dir():
        print(f"[ERROR] Not a directory: {root}")
        sys.exit(1)

    default_query = (
        "What files in this folder look like junk, temporary clutter, "
        "build artifacts, or files I can safely delete?"
    )
    query = _get("--query", default_query)

    return root, query, dry_run, keep_store


async def _run(root: Path, query: str, dry_run: bool, keep_store: bool) -> None:
    from services.embedding import pipeline
    import services.actions as action_store
    from services.roots import clear as clear_roots

    tmp = tempfile.mkdtemp(prefix="wisp_e2e_")
    pipeline.init_store(db_path=tmp)

    print("\n" + "=" * _WIDTH)
    print("  Wisp -- End-to-End Flow Test")
    print("=" * _WIDTH)
    print(f"  Target folder : {root}")
    print(f"  Query         : {query[:60]}")
    print(f"  LanceDB store : {tmp}")
    print(f"  Dry-run       : {dry_run}")

    try:
        # Flow 1
        candidates = await phase_scan(root)

        # Flow 2
        phase_search(query)

        # Flow 3a -- assistant + proposals
        proposals = await phase_assistant(query)

        # Flow 3b -- merge + interactive apply
        phase_execute(candidates, proposals, dry_run)

    finally:
        pipeline.teardown_store()
        if not keep_store:
            shutil.rmtree(tmp, ignore_errors=True)
        clear_roots()
        action_store.clear()
        print()


def main() -> None:
    if not _require_api_key():
        sys.exit(1)

    root, query, dry_run, keep_store = _parse_args()
    asyncio.run(_run(root, query, dry_run, keep_store))


if __name__ == "__main__":
    main()

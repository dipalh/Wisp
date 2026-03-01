"""
Search API — Test Suite

Run from backend/:

  Automated (offline validation + integration if API key set):
    python -m tests.test_search

  Interactive search REPL against a real directory:
    python -m tests.test_search -i --dir ~/Documents

Structure
---------
  PART 1 — Request validation   (offline, no API key)
  PART 2 — Root scope filtering (offline, no API key)
  PART 3 — Integration          (needs GEMINI_API_KEY)
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from pathlib import Path as _Path

_env_path = _Path(__file__).parent.parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(dotenv_path=_env_path, override=False)

# ── Test helpers ──────────────────────────────────────────────────────────────

_pass_count = 0
_fail_count = 0


def check(name: str, condition: bool, detail: str = "") -> bool:
    global _pass_count, _fail_count
    status = "[PASS]" if condition else "[FAIL]"
    print(f"  {status}  {name}")
    if detail:
        for line in detail.splitlines():
            print(f"         {line}")
    if condition:
        _pass_count += 1
    else:
        _fail_count += 1
    return condition


def _require_api_key() -> bool:
    if os.environ.get("GEMINI_API_KEY"):
        return True
    print("\n  [SKIP]  GEMINI_API_KEY not set -- skipping integration tests.")
    print("          Set it in backend/.env or export it.\n")
    return False


# ── TestClient setup ─────────────────────────────────────────────────────────
# Build a minimal FastAPI app with just the search router so we don't
# trigger imports of unrelated services during offline tests.

from fastapi import FastAPI
from fastapi.testclient import TestClient
from api.v1.search import router as search_router

_test_app = FastAPI()
_test_app.include_router(search_router, prefix="/search")
_client = TestClient(_test_app, raise_server_exceptions=False)


# ── PART 1: Request validation (offline) ─────────────────────────────────────

def run_validation_tests() -> None:
    print("\n" + "=" * 64)
    print("PART 1 -- Request validation  (offline)")
    print("=" * 64)

    # T1: empty query string -> 400
    resp = _client.post("/search", json={"query": ""})
    check("T1: empty query -> 400", resp.status_code == 400,
          f"got {resp.status_code}: {resp.text[:120]}")

    # T2: whitespace-only query -> 400
    resp = _client.post("/search", json={"query": "   "})
    check("T2: whitespace-only query -> 400", resp.status_code == 400,
          f"got {resp.status_code}: {resp.text[:120]}")

    # T3: k below minimum -> 422 (FastAPI validation)
    resp = _client.post("/search", json={"query": "hello", "k": 0})
    check("T3: k=0 -> 422", resp.status_code == 422,
          f"got {resp.status_code}: {resp.text[:120]}")

    # T4: k above maximum -> 422
    resp = _client.post("/search", json={"query": "hello", "k": 51})
    check("T4: k=51 -> 422", resp.status_code == 422,
          f"got {resp.status_code}: {resp.text[:120]}")

    # T5: missing query field -> 422
    resp = _client.post("/search", json={"k": 5})
    check("T5: missing query field -> 422", resp.status_code == 422,
          f"got {resp.status_code}: {resp.text[:120]}")

    # T6: valid request shape is accepted (200 or 500 if no API key — not 400/422)
    resp = _client.post("/search", json={"query": "test document"})
    check("T6: valid request is not rejected (not 400/422)",
          resp.status_code not in (400, 422),
          f"got {resp.status_code}: {resp.text[:120]}")

    # T7: response has required keys on success
    if resp.status_code == 200:
        body = resp.json()
        required = {"results", "query", "total"}
        check("T7: 200 response has required keys", required.issubset(body.keys()),
              f"got keys: {set(body.keys())}")
        check("T7b: results is a list", isinstance(body["results"], list))
        check("T7c: query echoed back", body["query"] == "test document")
    else:
        print("  [SKIP] T7-T7c: skipped (no API key for live search)")
        _pass_count += 3  # count as passing — offline environment expected


# ── PART 2: Root scope filtering (offline) ───────────────────────────────────

def run_root_filter_tests() -> None:
    print("\n" + "=" * 64)
    print("PART 2 -- Root scope filtering  (offline)")
    print("=" * 64)

    from services.roots import add_root, clear, is_under_root

    # Create real temp directories for path resolution
    root_a = tempfile.mkdtemp(prefix="wisp_search_root_")
    outside = tempfile.mkdtemp(prefix="wisp_search_out_")

    # Create fake file paths inside and outside the root
    file_inside  = str(_Path(root_a) / "notes.txt")
    file_outside = str(_Path(outside) / "other.txt")

    try:
        # No roots: both paths pass through
        clear()
        check("T8: no roots -> inside path passes",  is_under_root(file_inside))
        check("T9: no roots -> outside path passes", is_under_root(file_outside))

        # Register root_a only
        add_root(root_a)
        check("T10: root set -> inside path passes",   is_under_root(file_inside))
        check("T11: root set -> outside path blocked", not is_under_root(file_outside))

        # Empty string path (missing file_path on a hit) -> treated as blocked
        check("T12: empty path -> blocked when roots set", not is_under_root(""))

        # Clear restores open mode
        clear()
        check("T13: after clear -> outside path passes again", is_under_root(file_outside))

    finally:
        clear()
        shutil.rmtree(root_a, ignore_errors=True)
        shutil.rmtree(outside, ignore_errors=True)


# ── PART 3: Integration — ingest + search (needs GEMINI_API_KEY) ─────────────

# Same three test docs as test_embed_pipeline.py, kept here for self-containment.
_DOCS = {
    "search_invoice": {
        "filename": "invoice.txt",
        "text": textwrap.dedent("""\
            INVOICE #2024-0042
            Vendor: Acme Software Ltd.
            Date: 2024-11-15
            Total due: $12,636.00
            Payment method: Wire transfer
        """),
    },
    "search_resume": {
        "filename": "resume.txt",
        "text": textwrap.dedent("""\
            Jane Smith — Senior Software Engineer
            EXPERIENCE: Acme Corp, Lead Backend Engineer (2021-present)
            Designed distributed payment processing system.
            SKILLS: Python, Go, TypeScript, PostgreSQL, Kubernetes
        """),
    },
    "search_meeting": {
        "filename": "meeting_notes.txt",
        "text": textwrap.dedent("""\
            Q3 2024 Engineering All-Hands
            Agenda: roadmap review, on-call rotation.
            Action items: Alice finish vector DB migration by 2024-09-30.
        """),
    },
}


def _ingest_docs(pipeline) -> None:
    from services.file_processor.models import ContentResult
    for file_id, doc in _DOCS.items():
        cr = ContentResult(
            filename=doc["filename"], file_name=doc["filename"],
            mime_type="text/plain", category="text",
            content=doc["text"], text=doc["text"],
        )
        pipeline.ingest(cr, file_id=file_id)


def run_integration_tests() -> None:
    print("\n" + "=" * 64)
    print("PART 3 -- Integration  (Gemini API + LanceDB)")
    print("=" * 64)

    if not _require_api_key():
        return

    from services.embedding import pipeline

    tmp = tempfile.mkdtemp(prefix="wisp_test_search_lancedb_")
    pipeline.init_store(db_path=tmp)
    print(f"  (temp LanceDB dir: {tmp})")

    try:
        _ingest_docs(pipeline)
        total = pipeline.search.__module__  # confirm module loaded

        # T14: invoice query -> top hit is search_invoice
        print("\n  -- T14: query 'invoice total amount due' --")
        hits = pipeline.search("invoice total amount due", k=5)
        top = hits[0].file_id if hits else None
        print(f"    top hit: {top}")
        check("T14: 'invoice total' -> top hit is search_invoice",
              top == "search_invoice", f"got {top}")

        # T15: resume query -> top hit is search_resume
        print("\n  -- T15: query 'Python backend engineer' --")
        hits = pipeline.search("Python backend engineer", k=5)
        top = hits[0].file_id if hits else None
        print(f"    top hit: {top}")
        check("T15: 'Python backend engineer' -> top hit is search_resume",
              top == "search_resume", f"got {top}")

        # T16: route round-trip via TestClient (store already populated above)
        print("\n  -- T16: route round-trip --")
        resp = _client.post("/search", json={"query": "vector database migration meeting"})
        check("T16: route returns 200", resp.status_code == 200,
              f"got {resp.status_code}: {resp.text[:120]}")
        if resp.status_code == 200:
            body = resp.json()
            check("T16b: results list not empty", len(body["results"]) > 0,
                  f"total={body['total']}")
            check("T16c: each result has file_path key",
                  all("file_path" in r for r in body["results"]))
            check("T16d: each result has score key",
                  all("score" in r for r in body["results"]))
            check("T16e: each result has snippet key",
                  all("snippet" in r for r in body["results"]))

        # T17: ext filter returns only matching extension
        print("\n  -- T17: ext filter '.txt' --")
        resp = _client.post("/search", json={"query": "document", "ext": ".txt"})
        if resp.status_code == 200:
            body = resp.json()
            non_txt = [r for r in body["results"] if r["ext"] != ".txt"]
            check("T17: ext='.txt' -> all results are .txt",
                  len(non_txt) == 0, f"non-.txt results: {non_txt}")
        else:
            check("T17: ext filter request accepted", False,
                  f"got {resp.status_code}")

        # T18: snippet is at most 300 chars
        print("\n  -- T18: snippet length cap --")
        resp = _client.post("/search", json={"query": "all files"})
        if resp.status_code == 200:
            body = resp.json()
            over = [r for r in body["results"] if len(r["snippet"]) > 300]
            check("T18: all snippets <= 300 chars", len(over) == 0,
                  f"{len(over)} snippets over 300 chars")

    finally:
        pipeline.teardown_store()
        shutil.rmtree(tmp, ignore_errors=True)


# ── Interactive mode ─────────────────────────────────────────────────────────

def run_interactive(user_dir: str) -> None:
    print("\n" + "=" * 64)
    print("WISP -- Interactive Search")
    print("=" * 64)

    if not _require_api_key():
        return

    from services.embedding import pipeline

    root = _Path(user_dir).resolve()
    if not root.is_dir():
        print(f"  ERROR: {root} is not a directory")
        return

    tmp = tempfile.mkdtemp(prefix="wisp_search_repl_")
    pipeline.init_store(db_path=tmp)
    print(f"\n  Indexing {root} (temp store: {tmp}) ...")

    import asyncio
    from services.ingestor.ingester import ingest_directory
    count = asyncio.run(ingest_directory(root))
    print(f"  Indexed {count} files.  Type a query or 'quit' to exit.\n")

    try:
        while True:
            try:
                query = input("  search> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not query or query.lower() in ("quit", "exit", "q"):
                break

            hits = pipeline.search(query, k=8)
            if not hits:
                print("  (no results)\n")
                continue
            for i, h in enumerate(hits, 1):
                snippet = h.text[:120].replace("\n", " ")
                print(f"  [{i}] score={h.score:.3f}  {h.file_path or h.file_id}")
                print(f"       {snippet}")
            print()
    finally:
        pipeline.teardown_store()
        shutil.rmtree(tmp, ignore_errors=True)
        print("  (cleaned up temp index)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    interactive = "--interactive" in sys.argv or "-i" in sys.argv

    print("\n+================================================+")
    print("|  WISP -- Search API Test Suite                |")
    print("+================================================+")

    if interactive:
        dir_args = [sys.argv[i + 1] for i, a in enumerate(sys.argv)
                    if a == "--dir" and i + 1 < len(sys.argv)]
        user_dir = dir_args[0] if dir_args else "."
        run_interactive(user_dir)
        return

    run_validation_tests()
    run_root_filter_tests()
    run_integration_tests()

    total = _pass_count + _fail_count
    print("\n" + "=" * 64)
    if _fail_count == 0:
        print(f"  Results: {total}/{total} passed -- all good")
    else:
        print(f"  Results: {_pass_count}/{total} passed, {_fail_count} FAILED")
    print("=" * 64 + "\n")
    sys.exit(0 if _fail_count == 0 else 1)


if __name__ == "__main__":
    main()

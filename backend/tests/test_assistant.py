"""
Assistant API — Test Suite

Run from backend/:

  Automated (offline validation + integration if API key set):
    python -m tests.test_assistant

  Interactive chat REPL with a real directory:
    python -m tests.test_assistant -i --dir ~/Downloads

Structure
---------
  PART 1 — Request validation       (offline, no API key)
  PART 2 — Response shape           (offline, stubbed pipeline)
  PART 3 — Proposal integration     (offline, real junk files + stubbed pipeline)
  PART 4 — Full end-to-end          (needs GEMINI_API_KEY)
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import textwrap

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock, patch

_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(dotenv_path=_env_path, override=False)

from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.actions as action_store
from api.v1.assistant import router as assistant_router

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
    return False


# ── TestClient ────────────────────────────────────────────────────────────────

_app = FastAPI()
_app.include_router(assistant_router, prefix="/assistant")
_client = TestClient(_app, raise_server_exceptions=False)


# ── Stub helpers ──────────────────────────────────────────────────────────────

@dataclass
class _FakeHit:
    file_path:   str
    file_id:     str   = "fid"
    depth:       str   = "deep"
    text:        str   = "some content"
    score:       float = 0.9
    ext:         str   = ".txt"
    chunk_id:    str   = "c:0"
    chunk_index: int   = 0
    tags:        list  = field(default_factory=list)
    metadata:    dict  = field(default_factory=dict)


@dataclass
class _FakeAskResult:
    answer:         str
    hits:           list
    query:          str
    deepened_files: list = field(default_factory=list)


# ── PART 1: Request validation (offline) ─────────────────────────────────────

def run_validation_tests() -> None:
    print("\n" + "=" * 64)
    print("PART 1 -- Request validation  (offline)")
    print("=" * 64)

    # T1: empty query -> 400
    resp = _client.post("/assistant", json={"query": ""})
    check("T1: empty query -> 400", resp.status_code == 400,
          f"got {resp.status_code}: {resp.text[:120]}")

    # T2: whitespace-only -> 400
    resp = _client.post("/assistant", json={"query": "   "})
    check("T2: whitespace-only -> 400", resp.status_code == 400,
          f"got {resp.status_code}: {resp.text[:120]}")

    # T3: k out of range -> 422
    resp = _client.post("/assistant", json={"query": "hello", "k": 0})
    check("T3: k=0 -> 422", resp.status_code == 422,
          f"got {resp.status_code}")

    resp = _client.post("/assistant", json={"query": "hello", "k": 51})
    check("T4: k=51 -> 422", resp.status_code == 422,
          f"got {resp.status_code}")

    # T5: missing query -> 422
    resp = _client.post("/assistant", json={"k": 5})
    check("T5: missing query -> 422", resp.status_code == 422,
          f"got {resp.status_code}")

    # T6: valid request structure is not rejected (200 or 502 without store)
    resp = _client.post("/assistant", json={"query": "what files do I have?"})
    check("T6: valid request not rejected (not 400/422)",
          resp.status_code not in (400, 422),
          f"got {resp.status_code}: {resp.text[:120]}")


# ── PART 2: Response shape with stubbed pipeline ──────────────────────────────

def run_shape_tests() -> None:
    print("\n" + "=" * 64)
    print("PART 2 -- Response shape  (stubbed pipeline)")
    print("=" * 64)

    action_store.clear()

    stub_result = _FakeAskResult(
        answer="You have 3 documents.",
        hits=[_FakeHit(file_path="/fake/notes.txt", file_id="a")],
        query="what files do I have?",
    )

    with patch("api.v1.assistant.pipeline.ask", new=AsyncMock(return_value=stub_result)):
        resp = _client.post("/assistant", json={"query": "what files do I have?"})

    check("T7: stubbed ask -> 200", resp.status_code == 200,
          f"got {resp.status_code}: {resp.text[:200]}")

    if resp.status_code == 200:
        body = resp.json()
        required = {"answer", "proposals", "query", "sources", "deepened_files"}
        check("T8: all required keys present",
              required.issubset(body.keys()),
              f"got keys: {set(body.keys())}")
        check("T9: answer is a non-empty string",
              isinstance(body["answer"], str) and len(body["answer"]) > 0,
              f"got: {body['answer']!r}")
        check("T10: proposals is a list",
              isinstance(body["proposals"], list))
        check("T11: query echoed back",
              body["query"] == "what files do I have?")
        check("T12: sources is a list",
              isinstance(body["sources"], list))
        check("T13: deepened_files is a list",
              isinstance(body["deepened_files"], list))
        # Source from the stub hit should appear
        check("T14: stub file_path appears in sources",
              "/fake/notes.txt" in body["sources"],
              f"sources={body['sources']}")

    action_store.clear()


# ── PART 3: Proposals generated for junk files in hits ───────────────────────

def run_proposal_generation_tests() -> None:
    print("\n" + "=" * 64)
    print("PART 3 -- Proposals generated for junk files  (stubbed pipeline)")
    print("=" * 64)

    action_store.clear()

    # Create a real junk temp file so proposer can stat it
    junk = tempfile.NamedTemporaryFile(suffix=".tmp", delete=False)
    junk.write(b"junk content")
    junk.close()
    junk_path = junk.name

    clean = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
    clean.write(b"important content")
    clean.close()
    clean_path = clean.name

    stub_result = _FakeAskResult(
        answer="I found some files including a temp file.",
        hits=[
            _FakeHit(file_path=junk_path,  file_id="j1", ext=".tmp"),
            _FakeHit(file_path=clean_path, file_id="c1", ext=".pdf"),
        ],
        query="show me all files",
    )

    try:
        with patch("api.v1.assistant.pipeline.ask", new=AsyncMock(return_value=stub_result)):
            resp = _client.post("/assistant", json={"query": "show me all files"})

        check("T15: request succeeds", resp.status_code == 200,
              f"got {resp.status_code}: {resp.text[:120]}")

        if resp.status_code == 200:
            body = resp.json()
            proposals = body["proposals"]
            prop_paths = {p["file_path"] for p in proposals}
            check("T16: junk .tmp file gets a proposal",
                  junk_path in prop_paths,
                  f"proposal paths: {prop_paths}")
            check("T17: clean .pdf does not get a proposal",
                  clean_path not in prop_paths,
                  f"proposal paths: {prop_paths}")
            check("T18: proposals have required keys",
                  all({"action_id", "file_path", "junk_score", "reasons",
                       "action_type", "label"}.issubset(p.keys())
                      for p in proposals),
                  f"proposals: {proposals}")
            # Actions were recorded in the store
            stored = action_store.get_all()
            check("T19: proposals recorded in action store",
                  len(stored) == len(proposals),
                  f"store has {len(stored)}, proposals has {len(proposals)}")
    finally:
        Path(junk_path).unlink(missing_ok=True)
        Path(clean_path).unlink(missing_ok=True)
        # Clean up quarantine dir if created
        for p in [junk_path, clean_path]:
            q = Path(p).parent / ".wisp_quarantine"
            if q.exists():
                shutil.rmtree(q, ignore_errors=True)
        action_store.clear()


# ── PART 4: Full end-to-end integration ──────────────────────────────────────

_DOCS = {
    "asst_invoice": {
        "filename": "invoice.txt",
        "text": textwrap.dedent("""\
            INVOICE #2024-0042  Vendor: Acme Software Ltd.
            Total due: $12,636.00  Payment method: Wire transfer
        """),
    },
    "asst_resume": {
        "filename": "resume.txt",
        "text": textwrap.dedent("""\
            Jane Smith -- Senior Software Engineer
            Skills: Python, Go, TypeScript, PostgreSQL, Kubernetes
            Experience: Lead Backend at Acme Corp 2021-present
        """),
    },
}


def run_integration_tests() -> None:
    print("\n" + "=" * 64)
    print("PART 4 -- Full end-to-end  (Gemini API + LanceDB)")
    print("=" * 64)

    if not _require_api_key():
        return

    from services.embedding import pipeline
    from services.file_processor.models import ContentResult

    tmp = tempfile.mkdtemp(prefix="wisp_test_asst_lancedb_")
    pipeline.init_store(db_path=tmp)
    print(f"  (temp LanceDB dir: {tmp})")

    try:
        # Ingest test docs
        for fid, doc in _DOCS.items():
            cr = ContentResult(
                filename=doc["filename"], file_name=doc["filename"],
                mime_type="text/plain", category="text",
                content=doc["text"], text=doc["text"],
            )
            pipeline.ingest(cr, file_id=fid)

        # T20: assistant route returns 200
        print("\n  -- T20: POST /assistant with invoice query --")
        resp = _client.post("/assistant", json={"query": "what invoices do I have?"})
        check("T20: returns 200", resp.status_code == 200,
              f"got {resp.status_code}: {resp.text[:200]}")

        if resp.status_code == 200:
            body = resp.json()

            # T21: answer is a meaningful string
            check("T21: answer is non-empty", len(body["answer"]) > 10,
                  f"answer={body['answer']!r}")

            # T22: sources list contains at least one path
            check("T22: sources list non-empty", len(body["sources"]) > 0,
                  f"sources={body['sources']}")

            # T23: at least one source is the invoice
            invoice_in_sources = any(
                "invoice" in s.lower() for s in body["sources"]
            )
            check("T23: invoice file in sources", invoice_in_sources,
                  f"sources={body['sources']}")

        # T24: auto_deepen=False still returns 200
        print("\n  -- T24: auto_deepen=False --")
        resp2 = _client.post("/assistant",
                              json={"query": "Python engineer skills",
                                    "auto_deepen": False})
        check("T24: auto_deepen=False -> 200", resp2.status_code == 200,
              f"got {resp2.status_code}")

        # T25: ext filter narrows retrieval
        print("\n  -- T25: ext filter --")
        resp3 = _client.post("/assistant",
                              json={"query": "any documents", "ext": ".txt"})
        check("T25: ext='.txt' -> 200", resp3.status_code == 200,
              f"got {resp3.status_code}")

    finally:
        pipeline.teardown_store()
        shutil.rmtree(tmp, ignore_errors=True)
        action_store.clear()


# ── Interactive mode ─────────────────────────────────────────────────────────

def run_interactive(user_dir: str) -> None:
    print("\n" + "=" * 64)
    print("WISP -- Interactive Assistant")
    print("=" * 64)

    if not _require_api_key():
        return

    import asyncio
    from services.embedding import pipeline
    from services.ingestor.ingester import ingest_directory

    root = Path(user_dir).resolve()
    if not root.is_dir():
        print(f"  ERROR: {root} is not a directory")
        return

    tmp = tempfile.mkdtemp(prefix="wisp_asst_repl_")
    pipeline.init_store(db_path=tmp)
    print(f"\n  Indexing {root} ...")
    count = asyncio.run(ingest_directory(root))
    print(f"  Indexed {count} files.\n  Type a question or 'quit' to exit.\n")

    try:
        while True:
            try:
                query = input("  wisp> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not query or query.lower() in ("quit", "exit", "q"):
                break

            result = asyncio.run(pipeline.ask(query))
            width = min(shutil.get_terminal_size().columns - 6, 78)
            border = "-" * (width - 2)
            print(f"\n  +{border}+")
            for line in result.answer.splitlines():
                for wrapped in textwrap.wrap(line, width=width - 4) or [""]:
                    pad = " " * (width - 2 - len(wrapped))
                    print(f"  | {wrapped}{pad}|")
            print(f"  +{border}+")

            proposals = propose_from_hits(result.hits)
            if proposals:
                print(f"\n  Proposals ({len(proposals)}):")
                for p in proposals:
                    print(f"    [{p['action_id']}] {p['label']}")
            print()
    finally:
        pipeline.teardown_store()
        shutil.rmtree(tmp, ignore_errors=True)
        action_store.clear()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    interactive = "--interactive" in sys.argv or "-i" in sys.argv

    print("\n+================================================+")
    print("|  WISP -- Assistant API Test Suite             |")
    print("+================================================+")

    if interactive:
        dir_args = [sys.argv[i + 1] for i, a in enumerate(sys.argv)
                    if a == "--dir" and i + 1 < len(sys.argv)]
        user_dir = dir_args[0] if dir_args else "."
        run_interactive(user_dir)
        return

    run_validation_tests()
    run_shape_tests()
    run_proposal_generation_tests()
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

"""
Wisp — Embedding Pipeline Test Suite
=====================================

Run from the ``backend/`` directory:

  Automated (14 tests, exit 0 / 1):
    python -m tests.test_embed_pipeline

  Interactive (ingest 3 docs, then you type queries and see RAG answers):
    python -m tests.test_embed_pipeline --interactive

  Interactive with your own files:
    python -m tests.test_embed_pipeline --interactive --files path/to/a.txt path/to/b.md

Structure
---------
  PART 1 — Chunker unit tests          (offline, no API key needed)
  PART 2 — Full pipeline round-trip    (needs GEMINI_API_KEY in .env)

Both modes use an isolated temp LanceDB directory that is deleted on exit.
They never touch your real index.

Every test prints:
    INPUT     — what was given
    EXPECTED  — what we expect to see
    ACTUAL    — what the system returned
    [PASS] / [FAIL]

The interactive mode lets you TYPE a question and SEE an AI-generated answer
grounded in the indexed content, plus the raw retrieval chunks for transparency.
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
import textwrap

# ── allow  python -m tests.test_embed_pipeline  from backend/ ─────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Load .env so GEMINI_API_KEY is available
from pathlib import Path as _Path

_env_path = _Path(__file__).parent.parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(dotenv_path=_env_path, override=False)


# ═══════════════════════════════════════════════════════════════════════════════
# Test helpers
# ═══════════════════════════════════════════════════════════════════════════════

_pass_count = 0
_fail_count = 0


def check(name: str, condition: bool, detail: str = "") -> bool:
    """Print a single test verdict and track pass/fail counts."""
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


# ═══════════════════════════════════════════════════════════════════════════════
# PART 1 — Chunker  (no network, no vector store)
# ═══════════════════════════════════════════════════════════════════════════════

from services.embedding.chunker import chunk_text


def run_chunker_tests() -> None:
    print("\n" + "=" * 64)
    print("PART 1 — Chunker unit tests  (offline)")
    print("=" * 64)

    # T1: empty → nothing
    chunks = chunk_text("", file_id="f1")
    check("T1: empty text → 0 chunks", len(chunks) == 0, f"got {len(chunks)}")

    # T2: short text → exactly 1 chunk, text preserved
    short = "This is a short document about invoices."
    chunks = chunk_text(short, file_id="f2")
    t2_text = repr(chunks[0].text) if chunks else "—"
    check(
        "T2: short text → 1 chunk with matching text",
        len(chunks) == 1 and chunks[0].text == short,
        f"got {len(chunks)} chunk(s), text={t2_text}",
    )

    # T3: chunk_id format
    t3_id = repr(chunks[0].chunk_id) if chunks else "—"
    check(
        "T3: chunk_id == '<file_id>:<index>'",
        len(chunks) == 1 and chunks[0].chunk_id == "f2:0",
        f"got chunk_id={t3_id}",
    )

    # T4: long text → multiple chunks, no data lost
    long_text = ("word " * 200).strip()  # ~1 000 chars
    chunks = chunk_text(long_text, file_id="f3", chunk_size=200, overlap=20)
    joined = " ".join(c.text for c in chunks)
    all_present = all(w in joined for w in long_text.split())
    check("T4: long text → multiple chunks", len(chunks) > 1, f"got {len(chunks)} chunks")
    check("T4b: no words lost across chunks", all_present)

    # T5: paragraph-aware splitting
    para = "First paragraph.\n\nSecond paragraph."
    chunks = chunk_text(para, file_id="f4", chunk_size=800)
    check("T5: two paragraphs → 2 chunks", len(chunks) == 2, f"got {len(chunks)}")

    # T6: chunk indices are sequential 0-based
    chunks = chunk_text("A.\n\nB.\n\nC.", file_id="f5", chunk_size=800)
    indices = [c.chunk_index for c in chunks]
    check("T6: indices are 0-based sequential", indices == list(range(len(chunks))), f"got {indices}")


# ═══════════════════════════════════════════════════════════════════════════════
# Test documents (used by Part 2 and interactive mode)
# ═══════════════════════════════════════════════════════════════════════════════

DOCS = {
    "file_invoice": {
        "filename": "invoice.txt",
        "text": textwrap.dedent("""\
            INVOICE #2024-0042

            Vendor: Acme Software Ltd.
            Date: 2024-11-15
            Due: 2024-12-15

            Line items:
              - Enterprise license (12 months)  $4,800.00
              - Professional services (40 hrs)  $6,000.00
              - Support package (Basic)           $900.00

            Subtotal:   $11,700.00
            Tax (8 %):     $936.00
            Total due:  $12,636.00

            Payment method: Wire transfer
            Bank: First National Bank
            Account: 987-654-3210
        """),
    },
    "file_resume": {
        "filename": "resume.txt",
        "text": textwrap.dedent("""\
            Jane Smith
            Senior Software Engineer

            EXPERIENCE

            Acme Corp — Lead Backend Engineer (2021–present)
            - Designed distributed payment processing system, handling $2M/day.
            - Migrated monolith to microservices; reduced p99 latency by 40%.
            - Mentored team of 6 engineers.

            Startup XYZ — Python Developer (2018–2021)
            - Built REST APIs with FastAPI and PostgreSQL.
            - Automated CI/CD pipelines with GitHub Actions.

            SKILLS
            Python, Go, TypeScript, PostgreSQL, Redis, Kubernetes, Docker

            EDUCATION
            B.Sc. Computer Science, State University, 2018
        """),
    },
    "file_meeting": {
        "filename": "meeting_notes.txt",
        "text": textwrap.dedent("""\
            Q3 2024 — Engineering All-Hands Notes

            Attendees: Alice, Bob, Carol, David
            Date: 2024-09-10

            Agenda item 1: Roadmap review
            The team reviewed Q3 milestones. The new search feature is 80% complete.
            Alice noted the vector database migration would be finished by end of September.

            Agenda item 2: On-call rotation
            Bob volunteered to take the first October on-call shift.
            Carol raised concerns about alert fatigue — David will audit the alert rules.

            Action items:
            - Alice: finish vector DB migration by 2024-09-30
            - David: audit PagerDuty alert rules
            - Bob: confirm October on-call by 2024-09-12
        """),
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# Setup / teardown helpers  (used by both modes)
# ═══════════════════════════════════════════════════════════════════════════════


def _require_api_key() -> bool:
    """Return True if GEMINI_API_KEY is set, else print skip message."""
    if os.environ.get("GEMINI_API_KEY"):
        return True
    print("\n  [SKIP]  GEMINI_API_KEY not set — skipping pipeline tests.")
    print("          Set it in backend/.env or export it.\n")
    return False


def _create_temp_store() -> str:
    """Create a temp LanceDB dir and init the store there.
    Returns the temp dir path (caller must shutil.rmtree it).
    """
    from services.embedding import pipeline
    tmp = tempfile.mkdtemp(prefix="wisp_test_lancedb_")
    pipeline.init_store(db_path=tmp)
    print(f"  (temp LanceDB dir: {tmp})")
    return tmp


def _ingest_test_docs() -> dict[str, int]:
    """Ingest the three test docs.  Returns {file_id: chunk_count}."""
    from services.embedding import pipeline
    from services.file_processor.models import ContentResult

    counts: dict[str, int] = {}
    for file_id, doc in DOCS.items():
        cr = ContentResult(
            filename=doc["filename"],
            file_name=doc["filename"],
            mime_type="text/plain",
            category="text",
            content=doc["text"],
            text=doc["text"],
        )
        result = pipeline.ingest(cr, file_id=file_id)
        counts[file_id] = result.chunk_count
        if result.errors:
            print(f"    WARNING: {file_id} → errors: {result.errors}")
    return counts


# ═══════════════════════════════════════════════════════════════════════════════
# PART 2 — Full pipeline round-trip
# ═══════════════════════════════════════════════════════════════════════════════


def run_pipeline_tests() -> None:
    print("\n" + "=" * 64)
    print("PART 2 — Pipeline round-trip  (Gemini API + LanceDB)")
    print("=" * 64)

    if not _require_api_key():
        return

    from services.embedding import pipeline, store

    tmp = _create_temp_store()
    try:
        _run_pipeline_checks(pipeline, store)
    finally:
        pipeline.teardown_store()
        shutil.rmtree(tmp, ignore_errors=True)


def _run_pipeline_checks(pipeline, store) -> None:
    # ── T7 + T8: ingest all 3 docs ───────────────────────────────────────────
    print("\n  ── T7/T8: Ingest all documents ──")
    counts = _ingest_test_docs()
    invoice_count = counts.get("file_invoice", 0)
    total = store.collection_count()
    print(f"    INPUT    : 3 documents ({sum(len(d['text']) for d in DOCS.values())} chars total)")
    print(f"    EXPECTED : each file produces >0 chunks")
    print(f"    ACTUAL   : invoice={invoice_count}, resume={counts.get('file_resume',0)}, "
          f"meeting={counts.get('file_meeting',0)}, total={total}")
    check("T7: invoice chunk_count > 0", invoice_count > 0)
    check("T8: all three → total > 0", total > 0, f"total={total}")

    # ── T9: semantic query → invoice ──────────────────────────────────────────
    print("\n  ── T9: Query 'invoice total amount due' ──")
    hits = pipeline.search("invoice total amount due", k=3)
    _print_hits("invoice total amount due", "file_invoice", hits)
    check("T9: top hit is file_invoice", hits and hits[0].file_id == "file_invoice")

    # ── T10: semantic query → resume ──────────────────────────────────────────
    print("\n  ── T10: Query 'Python backend engineer experience' ──")
    hits = pipeline.search("Python backend engineer experience", k=3)
    _print_hits("Python backend engineer experience", "file_resume", hits)
    check("T10: top hit is file_resume", hits and hits[0].file_id == "file_resume")

    # ── T11: idempotency ──────────────────────────────────────────────────────
    print("\n  ── T11: Re-ingest invoice (idempotency) ──")
    before = store.collection_count()
    from services.file_processor.models import ContentResult
    cr = ContentResult(
        filename="invoice.txt", file_name="invoice.txt",
        mime_type="text/plain", category="text",
        content=DOCS["file_invoice"]["text"], text=DOCS["file_invoice"]["text"],
    )
    pipeline.ingest(cr, file_id="file_invoice")
    after = store.collection_count()
    print(f"    INPUT    : re-ingest same invoice.txt")
    print(f"    EXPECTED : chunk count unchanged (no duplicates)")
    print(f"    ACTUAL   : before={before}, after={after}")
    check("T11: re-ingest → count unchanged", before == after)

    # ── T12: delete ───────────────────────────────────────────────────────────
    print("\n  ── T12: Delete invoice ──")
    before = store.collection_count()
    pipeline.delete_file("file_invoice")
    after = store.collection_count()
    removed = before - after
    print(f"    INPUT    : delete_file('file_invoice')")
    print(f"    EXPECTED : count decreases by {invoice_count}")
    print(f"    ACTUAL   : before={before}, after={after}, removed={removed}")
    check("T12: delete removes correct chunks", removed == invoice_count)

    # ── T13: query after delete ───────────────────────────────────────────────
    print("\n  ── T13: Query after delete ──")
    hits = pipeline.search("invoice total amount due", k=3)
    found = any(h.file_id == "file_invoice" for h in hits)
    print(f"    EXPECTED : file_invoice NOT in results")
    print(f"    ACTUAL   :")
    for i, h in enumerate(hits):
        print(f"      [{i+1}] file_id={h.file_id}  score={h.score:.4f}")
    check("T13: deleted file absent from results", not found)


def _print_hits(query: str, expected_top: str, hits) -> None:
    print(f"    INPUT    : query = {query!r}")
    print(f"    EXPECTED : top hit from {expected_top}")
    print(f"    ACTUAL   :")
    for i, h in enumerate(hits):
        print(f"      [{i+1}] file_id={h.file_id}  score={h.score:.4f}")
        # Show up to 100 chars of the chunk text so you can read it
        snippet = h.text[:100].replace("\n", " ")
        print(f"           \"{snippet}...\"")


# ═══════════════════════════════════════════════════════════════════════════════
# Interactive mode
# ═══════════════════════════════════════════════════════════════════════════════


def _ingest_user_files(file_paths: list[str]) -> dict[str, int]:
    """Read plain-text files from disk and ingest them into the pipeline."""
    import hashlib
    from services.embedding import pipeline
    from services.file_processor.models import ContentResult

    counts: dict[str, int] = {}
    for path in file_paths:
        p = _Path(path).resolve()
        if not p.is_file():
            print(f"    ⚠ skipping (not a file): {p}")
            continue
        text = p.read_text(errors="replace")
        file_id = hashlib.sha256(str(p).encode()).hexdigest()[:16]
        cr = ContentResult(
            filename=p.name,
            file_name=p.name,
            mime_type=p.suffix,
            category="text",
            content=text,
            text=text,
            engine_used="user-file",
            fallback_used=False,
            errors=[],
        )
        res = pipeline.ingest(cr, file_id)
        counts[file_id] = res.chunk_count
        print(f"    {p.name:30s}  →  {res.chunk_count} chunks")
    return counts


def run_interactive(user_files: list[str] | None = None) -> None:
    print("\n" + "=" * 64)
    print("INTERACTIVE MODE — ask questions, get AI answers")
    print("=" * 64)

    if not _require_api_key():
        return

    from services.embedding import pipeline, store

    tmp = _create_temp_store()
    try:
        if user_files:
            print(f"\n  Ingesting {len(user_files)} user-provided file(s)...")
            counts = _ingest_user_files(user_files)
        else:
            print("\n  Ingesting 3 test documents...")
            counts = _ingest_test_docs()

        total = store.collection_count()
        print(f"\n  Ready.  {total} chunks across {len(counts)} files.\n")

        if not user_files:
            print("  Documents available:")
            print("    • invoice.txt       — Acme Software invoice, $12,636.00")
            print("    • resume.txt        — Jane Smith, Senior Software Engineer")
            print("    • meeting_notes.txt — Q3 engineering all-hands")

        print()
        print("  Ask a natural-language question and press Enter.")
        print("  Type 'quit' or Ctrl-C to exit.\n")

        while True:
            try:
                query = input("  question> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not query or query.lower() in ("quit", "exit", "q"):
                break

            result = pipeline.ask(query, k=5)

            # ── AI Answer ─────────────────────────────────────────────────
            print()
            print("  ┌─ ANSWER ─────────────────────────────────────────────┐")
            for line in textwrap.wrap(result.answer, width=64):
                print(f"  │ {line}")
            print("  └─────────────────────────────────────────────────────┘")

            # ── Raw retrieved chunks (for transparency / debugging) ───────
            if result.hits:
                print()
                print("  Retrieved chunks (for transparency):")
                for i, h in enumerate(result.hits):
                    label = h.file_path or h.file_id
                    print(f"    [{i+1}] {label}  (score={h.score:.4f})")
                    snippet = h.text[:120].replace("\n", " ")
                    print(f"        \"{snippet}...\"")
            print()

    finally:
        pipeline.teardown_store()
        shutil.rmtree(tmp, ignore_errors=True)
        print("  (cleaned up temp LanceDB dir)")


# ═══════════════════════════════════════════════════════════════════════════════
# Main entry point
# ═══════════════════════════════════════════════════════════════════════════════


def _parse_files_arg() -> list[str]:
    """Extract file paths following --files from sys.argv."""
    if "--files" not in sys.argv:
        return []
    idx = sys.argv.index("--files") + 1
    # Collect everything after --files that isn't another flag
    paths: list[str] = []
    while idx < len(sys.argv) and not sys.argv[idx].startswith("-"):
        paths.append(sys.argv[idx])
        idx += 1
    return paths


def main() -> None:
    interactive = "--interactive" in sys.argv or "-i" in sys.argv

    print("\n╔════════════════════════════════════════╗")
    print("║  WISP — Embedding Pipeline Test Suite  ║")
    print("╚════════════════════════════════════════╝")

    if interactive:
        user_files = _parse_files_arg()
        run_interactive(user_files=user_files or None)
    else:
        run_chunker_tests()
        run_pipeline_tests()

        total = _pass_count + _fail_count
        print("\n" + "=" * 64)
        print(f"  Results: {_pass_count}/{total} passed", end="")
        if _fail_count:
            print(f"  — {_fail_count} FAILED")
        else:
            print("  — all good")
        print("=" * 64 + "\n")

        sys.exit(0 if _fail_count == 0 else 1)


if __name__ == "__main__":
    main()

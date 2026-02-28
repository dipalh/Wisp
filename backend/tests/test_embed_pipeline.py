"""
Manual end-to-end test for the embedding pipeline.

Run from the backend/ directory:

    python -m tests.test_embed_pipeline

What this does
--------------
  Part 1 — Chunker unit tests  (no API calls, instant)
  Part 2 — Full pipeline round-trip  (needs GEMINI_API_KEY + chromadb)

For Part 2 a fresh temporary Chroma collection is used (torn down after the
test), so it never pollutes your real index.

Each test prints:
    INPUT     — what was given
    EXPECTED  — what we expect to see
    ACTUAL    — what the system returned
    [PASS] / [FAIL]

Exit code: 0 = all passed, 1 = one or more failed.
"""
from __future__ import annotations

import os
import sys
import textwrap
import tempfile

# ── allow running as  python -m tests.test_embed_pipeline  from backend/ ──────
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Load .env from backend/ so GEMINI_API_KEY is available without preflight
from pathlib import Path as _Path
_env_path = _Path(__file__).parent.parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv as _load_dotenv
    _load_dotenv(dotenv_path=_env_path, override=False)


# ═════════════════════════════════════════════════════════════════════════════
# PART 1 — Chunker  (no network, no Chroma)
# ═════════════════════════════════════════════════════════════════════════════

from services.embedding.chunker import chunk_text


def _run_chunker_tests() -> list[bool]:
    results: list[bool] = []

    def check(name: str, condition: bool, detail: str = "") -> bool:
        status = "[PASS]" if condition else "[FAIL]"
        print(f"  {status}  {name}")
        if detail:
            print(f"         {detail}")
        results.append(condition)
        return condition

    print("\n" + "=" * 60)
    print("PART 1 — Chunker unit tests")
    print("=" * 60)

    # ── T1: empty string → no chunks ─────────────────────────────────────────
    chunks = chunk_text("", file_id="f1")
    check("T1: empty text → 0 chunks", len(chunks) == 0, f"got {len(chunks)}")

    # ── T2: short text → exactly 1 chunk ─────────────────────────────────────
    short = "This is a short document about invoices."
    chunks = chunk_text(short, file_id="f2")
    t2_text = repr(chunks[0].text) if chunks else "—"
    check(
        "T2: short text → 1 chunk",
        len(chunks) == 1 and chunks[0].text == short,
        f"got {len(chunks)} chunk(s), text={t2_text}",
    )

    # ── T3: chunk_id format ────────────────────────────────────────────────────
    t3_id = repr(chunks[0].chunk_id) if chunks else "—"
    check(
        "T3: chunk_id is '<file_id>:<index>'",
        len(chunks) == 1 and chunks[0].chunk_id == "f2:0",
        f"got chunk_id={t3_id}",
    )

    # ── T4: long text → multiple chunks without data loss ─────────────────────
    long_text = ("word " * 200).strip()   # 1 000 chars
    chunks = chunk_text(long_text, file_id="f3", chunk_size=200, overlap=20)
    joined = " ".join(c.text for c in chunks)
    # Every original word should appear somewhere in the joined chunks
    all_words_present = all(w in joined for w in long_text.split())
    check(
        "T4: long text → multiple chunks",
        len(chunks) > 1,
        f"got {len(chunks)} chunks",
    )
    check(
        "T4b: no words lost across chunks",
        all_words_present,
        "some words missing from joined output" if not all_words_present else "ok",
    )

    # ── T5: paragraph-aware splitting ─────────────────────────────────────────
    para_text = "First paragraph content here.\n\nSecond paragraph content here."
    chunks = chunk_text(para_text, file_id="f4", chunk_size=800)
    check(
        "T5: two paragraphs → 2 chunks",
        len(chunks) == 2,
        f"got {len(chunks)} chunks",
    )

    # ── T6: re-chunking same file_id produces correct indices ──────────────────
    chunks = chunk_text("Alpha.\n\nBeta.\n\nGamma.", file_id="myfile", chunk_size=800)
    indices = [c.chunk_index for c in chunks]
    check(
        "T6: chunk indices are 0-based sequential",
        indices == list(range(len(chunks))),
        f"got {indices}",
    )

    return results


# ═════════════════════════════════════════════════════════════════════════════
# PART 2 — Full pipeline round-trip  (needs GEMINI_API_KEY)
# ═════════════════════════════════════════════════════════════════════════════


# ── Fake documents ────────────────────────────────────────────────────────────

INVOICE_TEXT = textwrap.dedent("""\
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
""")

RESUME_TEXT = textwrap.dedent("""\
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
""")

MEETING_NOTES_TEXT = textwrap.dedent("""\
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
""")


def _run_pipeline_tests() -> list[bool]:
    print("\n" + "=" * 60)
    print("PART 2 — Full pipeline round-trip  (Gemini API + Chroma)")
    print("=" * 60)

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("\n  [SKIP] GEMINI_API_KEY not set — skipping pipeline tests.")
        print("         Set it in backend/.env or as an environment variable.\n")
        return []

    # ── Point Chroma at a temp directory so tests never pollute real data ──────
    tmp_dir = tempfile.mkdtemp(prefix="wisp_test_chroma_")
    os.environ["WISP_CHROMA_PATH"] = tmp_dir
    print(f"\n  (temp Chroma dir: {tmp_dir})")

    # Re-import store after env var is set so the client picks up the temp path
    import importlib
    from services.embedding import store as _store
    importlib.reload(_store)

    from services.embedding import pipeline
    importlib.reload(pipeline)

    from services.file_processor.models import ContentResult

    results: list[bool] = []

    def check(name: str, condition: bool, detail: str = "") -> bool:
        status = "[PASS]" if condition else "[FAIL]"
        print(f"  {status}  {name}")
        if detail:
            for line in detail.splitlines():
                print(f"         {line}")
        results.append(condition)
        return condition

    # ── Helper to build a minimal ContentResult ────────────────────────────────
    def make_result(text: str, filename: str) -> ContentResult:
        return ContentResult(
            filename=filename,
            file_name=filename,
            mime_type="text/plain",
            category="text",
            content=text,
            text=text,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # T7: Ingest a single document and confirm chunk_count > 0
    # ─────────────────────────────────────────────────────────────────────────
    print("\n  ── T7: Ingest invoice ──")
    ingest_result = pipeline.ingest(make_result(INVOICE_TEXT, "invoice.txt"), file_id="file_invoice")
    print(f"    INPUT    : invoice.txt  ({len(INVOICE_TEXT)} chars)")
    print(f"    EXPECTED : chunk_count > 0, no errors")
    print(f"    ACTUAL   : chunk_count={ingest_result.chunk_count}, errors={ingest_result.errors}")
    check(
        "T7: invoice ingested (chunks > 0)",
        ingest_result.chunk_count > 0 and not ingest_result.errors,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # T8: Ingest resume + meeting notes
    # ─────────────────────────────────────────────────────────────────────────
    print("\n  ── T8: Ingest resume + meeting notes ──")
    r_resume = pipeline.ingest(make_result(RESUME_TEXT, "resume.txt"), file_id="file_resume")
    r_meeting = pipeline.ingest(make_result(MEETING_NOTES_TEXT, "meeting_notes.txt"), file_id="file_meeting")
    total_chunks = _store.collection_count()
    print(f"    ACTUAL   : resume chunks={r_resume.chunk_count}, meeting chunks={r_meeting.chunk_count}")
    print(f"    ACTUAL   : total in Chroma={total_chunks}")
    check(
        "T8: all three files ingested (total > 0)",
        total_chunks > 0,
        f"total chunks in Chroma: {total_chunks}",
    )

    # ─────────────────────────────────────────────────────────────────────────
    # T9: Semantic query — "invoice total amount due" → should hit invoice
    # ─────────────────────────────────────────────────────────────────────────
    print("\n  ── T9: Query 'invoice total amount due' ──")
    hits = pipeline.search("invoice total amount due", k=3)
    print(f"    INPUT    : query = 'invoice total amount due'")
    print(f"    EXPECTED : top result from file_invoice")
    print(f"    ACTUAL   :")
    for i, h in enumerate(hits):
        print(f"      [{i+1}] file_id={h.file_id}  score={h.score:.4f}")
        print(f"           text={h.text[:80]!r}...")
    top_is_invoice = hits and hits[0].file_id == "file_invoice"
    check(
        "T9: 'invoice total' → top result is file_invoice",
        top_is_invoice,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # T10: Semantic query — "Python engineer experience" → should hit resume
    # ─────────────────────────────────────────────────────────────────────────
    print("\n  ── T10: Query 'Python backend engineer experience' ──")
    hits = pipeline.search("Python backend engineer experience", k=3)
    print(f"    INPUT    : query = 'Python backend engineer experience'")
    print(f"    EXPECTED : top result from file_resume")
    print(f"    ACTUAL   :")
    for i, h in enumerate(hits):
        print(f"      [{i+1}] file_id={h.file_id}  score={h.score:.4f}")
        print(f"           text={h.text[:80]!r}...")
    top_is_resume = hits and hits[0].file_id == "file_resume"
    check(
        "T10: 'Python engineer' → top result is file_resume",
        top_is_resume,
    )

    # ─────────────────────────────────────────────────────────────────────────
    # T11: Idempotency — re-ingest invoice, chunk count should stay the same
    # ─────────────────────────────────────────────────────────────────────────
    print("\n  ── T11: Re-ingest invoice (idempotency check) ──")
    count_before = _store.collection_count()
    pipeline.ingest(make_result(INVOICE_TEXT, "invoice.txt"), file_id="file_invoice")
    count_after = _store.collection_count()
    print(f"    INPUT    : same invoice.txt ingested again")
    print(f"    EXPECTED : chunk count stays the same (no duplicates)")
    print(f"    ACTUAL   : before={count_before}, after={count_after}")
    check(
        "T11: re-ingest does not add duplicate chunks",
        count_before == count_after,
        f"before={count_before} after={count_after}",
    )

    # ─────────────────────────────────────────────────────────────────────────
    # T12: delete_file removes that file's chunks
    # ─────────────────────────────────────────────────────────────────────────
    print("\n  ── T12: Delete invoice chunks ──")
    count_before = _store.collection_count()
    pipeline.delete_file("file_invoice")
    count_after = _store.collection_count()
    removed = count_before - count_after
    print(f"    INPUT    : delete_file('file_invoice')")
    print(f"    EXPECTED : chunk count decreases by invoice chunk count ({ingest_result.chunk_count})")
    print(f"    ACTUAL   : before={count_before}, after={count_after}, removed={removed}")
    check(
        "T12: delete_file removes the correct number of chunks",
        removed == ingest_result.chunk_count,
        f"expected to remove {ingest_result.chunk_count}, actually removed {removed}",
    )

    # ─────────────────────────────────────────────────────────────────────────
    # T13: Query after deletion — invoice chunks should NOT be top result
    # ─────────────────────────────────────────────────────────────────────────
    print("\n  ── T13: Query 'invoice total' after invoice deleted ──")
    hits = pipeline.search("invoice total amount due", k=3)
    invoice_in_results = any(h.file_id == "file_invoice" for h in hits)
    print(f"    EXPECTED : file_invoice does NOT appear in results")
    print(f"    ACTUAL   :")
    for i, h in enumerate(hits):
        print(f"      [{i+1}] file_id={h.file_id}  score={h.score:.4f}")
    check(
        "T13: deleted file no longer appears in search results",
        not invoice_in_results,
    )

    # ── Cleanup ───────────────────────────────────────────────────────────────
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    return results


# ═════════════════════════════════════════════════════════════════════════════
# Runner
# ═════════════════════════════════════════════════════════════════════════════


def main() -> None:
    print("\nWISP — Embedding Pipeline Tests")
    print("================================")

    all_results = _run_chunker_tests() + _run_pipeline_tests()

    passed = sum(all_results)
    total = len(all_results)
    failed = total - passed

    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} passed", end="")
    if failed:
        print(f"  ✗ {failed} FAILED")
    else:
        print("  — all good")
    print("=" * 60 + "\n")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()

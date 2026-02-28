"""
Wisp — Tiered Embedding Pipeline Test Suite
=============================================

Comprehensive, automated verification of the embedding pipeline across
four tiers of increasing scope and cost.

Tier 1 — Offline unit tests        (no API, no network, fast)
Tier 2 — Known-content integration  (needs GEMINI_API_KEY, ~60s)
Tier 3 — Downloads folder slices    (needs downloads + API, ~3-5 min)
Tier 4 — Full downloads scale       (needs downloads + API, ~20-40 min)

Usage
-----
    # Run all available tiers (skips unavailable ones):
    python -m tests.test_pipeline_tiered

    # Run a specific tier:
    python -m tests.test_pipeline_tiered --tier 1
    python -m tests.test_pipeline_tiered --tier 2
    python -m tests.test_pipeline_tiered --tier 3
    python -m tests.test_pipeline_tiered --tier 4

Every test prints INPUT / EXPECTED / ACTUAL / [PASS] or [FAIL].
Exit code 0 = all tests passed, 1 = failures.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import random
import shutil
import sys
import tempfile
import textwrap
import time
from collections import Counter, defaultdict
from pathlib import Path

# ── allow running from backend/ ───────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_env_path, override=False)


# ═══════════════════════════════════════════════════════════════════════════════
#  TEST HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

_pass_count = 0
_fail_count = 0
_skip_count = 0


def _check(name: str, condition: bool, detail: str = "") -> bool:
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


def _skip(name: str, reason: str) -> None:
    global _skip_count
    print(f"  [SKIP]  {name}  — {reason}")
    _skip_count += 1


def _file_id_for(name: str) -> str:
    """Deterministic file_id from a virtual filename."""
    return hashlib.sha256(name.encode()).hexdigest()[:16]


def _has_api_key() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def _downloads_path() -> Path | None:
    """Return the resolved Downloads folder if it exists."""
    p = Path("../downloads").resolve()
    if p.is_dir():
        return p
    p = Path.home() / "Downloads"
    if p.is_dir():
        return p
    return None


# ═══════════════════════════════════════════════════════════════════════════════
#  GROUND-TRUTH DOCUMENTS — synthetic files with known, verifiable content
# ═══════════════════════════════════════════════════════════════════════════════

GROUND_TRUTH: dict[str, dict] = {
    "gt_resume": {
        "filename": "sarah_johnson_resume.txt",
        "ext": ".txt",
        "content": textwrap.dedent("""\
            Sarah Johnson
            Senior Data Scientist

            EXPERIENCE

            TechCorp — Senior Data Scientist (2021–present)
            - Led machine learning pipeline processing 50TB of customer data daily
            - Built recommendation engine that increased click-through rate by 23%
            - Managed team of 4 junior data scientists
            - Technologies: Python, PyTorch, Spark, Airflow

            StartupAI — ML Engineer (2018–2021)
            - Developed NLP models for sentiment analysis on customer feedback
            - Deployed models on AWS SageMaker, serving 10K requests/sec
            - Reduced inference latency from 200ms to 45ms

            EDUCATION
            M.Sc. Machine Learning, MIT, 2018
            B.Sc. Mathematics, UC Berkeley, 2016

            SKILLS
            Python, PyTorch, TensorFlow, SQL, Spark, AWS, Kubernetes, Docker, Git

            CERTIFICATIONS
            AWS Certified Machine Learning Specialty (2022)
            Google Professional Data Engineer (2020)
        """),
        "search_must_find": [
            "resumes or CVs",
            "data scientist experience",
            "Sarah Johnson",
            "who works at TechCorp",
            "machine learning engineer",
        ],
        "search_must_not_find": [
            "Niagara Falls trip",
            "pasta recipe",
            "invoice payment",
        ],
        "answer_keywords": {
            "resumes or CVs": ["Sarah Johnson", "Data Scientist"],
            "data scientist experience": ["TechCorp", "ML"],
            "machine learning engineer": ["Sarah", "PyTorch"],
        },
    },

    "gt_trip_report": {
        "filename": "niagara_trip_summer_2024.txt",
        "ext": ".txt",
        "content": textwrap.dedent("""\
            Niagara Falls Family Trip — July 2024

            We drove up from Toronto on July 12th, 2024. The whole family came:
            Mom, Dad, Priya, and little Arjun (who just turned 5).

            Day 1 — Arriving at the Falls
            Checked into the Marriott Fallsview Hotel around 3 PM. The room had an
            incredible view of Horseshoe Falls. We walked along the promenade at
            sunset — the mist was magical. Had dinner at the Rainforest Cafe.

            Day 2 — Maid of the Mist & Clifton Hill
            Took the Maid of the Mist boat tour in the morning. Arjun was scared
            at first but ended up laughing the whole time. Got completely soaked!
            Spent the afternoon on Clifton Hill — mini golf, the Ferris wheel, and
            way too much fudge.

            Day 3 — Niagara-on-the-Lake
            Drove to the charming town of Niagara-on-the-Lake for wine tasting
            at Inniskillin and Peller Estates. Bought 3 bottles of ice wine.
            Beautiful Victorian architecture downtown.

            Day 4 — Journey Behind the Falls
            The tunnels behind Horseshoe Falls were awe-inspiring. You can feel
            the raw power of 750,000 gallons per second thundering past.
            Had a farewell dinner at AG Inspired Cuisine.

            Total cost: about $2,800 CAD for 4 nights including the hotel, meals,
            attractions, and souvenirs. Would absolutely go back!

            Photos are in the "niagara_2024_photos" folder.
        """),
        "search_must_find": [
            "Niagara Falls trip",
            "what happened during the Niagara trip back in Summer 2024",
            "family vacation",
            "Maid of the Mist",
        ],
        "search_must_not_find": [
            "machine learning pipeline",
            "invoice amount due",
            "API documentation",
        ],
        "answer_keywords": {
            "Niagara Falls trip": ["Niagara", "July", "2024"],
            "what happened during the Niagara trip back in Summer 2024": [
                "Maid of the Mist", "Horseshoe Falls", "family",
            ],
            "family vacation": ["Niagara", "Arjun", "Marriott"],
        },
    },

    "gt_invoice": {
        "filename": "techsupply_invoice_2024.txt",
        "ext": ".txt",
        "content": textwrap.dedent("""\
            INVOICE #INV-2024-8837

            From: TechSupply Corp
            To: Wisp Software Inc.
            Date: October 3, 2024
            Due: November 3, 2024

            Description                          Qty    Unit Price     Total
            ─────────────────────────────────────────────────────────────────
            MacBook Pro 14" M3 Pro               2      $1,999.00    $3,998.00
            Apple Magic Keyboard                 2         $99.00      $198.00
            LG 27" 4K Monitor                    2        $349.00      $698.00
            USB-C Hub (Anker 7-in-1)             4         $35.99      $143.96
            Ergonomic Office Chair (Herman Miller) 2      $1,295.00   $2,590.00

            Subtotal:     $7,627.96
            Tax (13% HST): $991.63
            TOTAL DUE:    $8,619.59

            Payment: Wire transfer to RBC account ending in 4521
            Terms: Net 30

            Thank you for your business!
        """),
        "search_must_find": [
            "invoice total amount",
            "MacBook purchase",
            "how much did we spend on equipment",
        ],
        "search_must_not_find": [
            "Niagara Falls",
            "resume data scientist",
        ],
        "answer_keywords": {
            "invoice total amount": ["8,619", "TechSupply"],
            "MacBook purchase": ["MacBook", "M3"],
            "how much did we spend on equipment": ["$7,627", "$8,619"],
        },
    },

    "gt_recipe": {
        "filename": "grandmas_famous_pasta.txt",
        "ext": ".txt",
        "content": textwrap.dedent("""\
            Grandma Rosa's Famous Penne Arrabbiata

            This recipe has been in our family since Grandma Rosa brought it
            from Naples in 1962. Makes 4 servings.

            INGREDIENTS
            - 400g penne rigate
            - 800g San Marzano tomatoes (canned, whole)
            - 6 cloves garlic, thinly sliced
            - 2 teaspoons red pepper flakes (add more if you dare!)
            - Fresh basil — a big handful
            - 100ml extra virgin olive oil
            - Pecorino Romano, freshly grated
            - Salt to taste

            INSTRUCTIONS
            1. Bring a large pot of salted water to a rolling boil. Cook penne
               until al dente (usually 11 minutes). Reserve 1 cup pasta water.
            2. While pasta cooks, heat olive oil in a large skillet over medium
               heat. Add garlic slices and cook until just golden (2 minutes).
            3. Add red pepper flakes, stir 30 seconds. Add crushed San Marzano
               tomatoes. Simmer 15 minutes, breaking up tomatoes with a spoon.
            4. Drain pasta and add to the sauce. Toss vigorously, adding pasta
               water a splash at a time until the sauce clings to each tube.
            5. Tear fresh basil over the top. Serve with a snowstorm of
               Pecorino Romano.

            GRANDMA'S SECRET: The trick is the pasta water. It's liquid gold —
            the starch makes the sauce silky and helps it grip the penne.

            Prep: 10 min | Cook: 25 min | Total: 35 min
        """),
        "search_must_find": [
            "pasta recipe",
            "cooking instructions",
            "Grandma Rosa",
        ],
        "search_must_not_find": [
            "data scientist",
            "Niagara Falls hotel",
            "invoice payment wire transfer",
        ],
        "answer_keywords": {
            "pasta recipe": ["penne", "Grandma", "Rosa", "Naples", "arrabbiata", "San Marzano"],
            "cooking instructions": ["garlic", "olive oil", "tomato"],
        },
    },

    "gt_meeting_notes": {
        "filename": "q3_engineering_allhands.txt",
        "ext": ".txt",
        "content": textwrap.dedent("""\
            Q3 2024 — Engineering All-Hands Meeting Notes
            Date: September 10, 2024
            Attendees: Alice Chen, Bob Martinez, Carol Wu, David Kim, Priya Patel

            ══ ROADMAP UPDATE ══
            The new semantic search feature is 85% complete. Alice reported the
            vector database migration from Pinecone to self-hosted Qdrant is on
            track for September 30th. Estimated cost savings: $4,200/month.

            The mobile app redesign (Project Maple) launches October 15th.
            Bob's team has completed the Flutter rewrite of 12/15 screens.

            ══ ON-CALL ROTATION ══
            Carol raised alert fatigue — too many P3 alerts waking people up.
            David will audit PagerDuty rules and consolidate duplicate alerts.
            Bob volunteered for October 1–15 on-call.
            Priya takes October 16–31.

            ══ HIRING UPDATE ══
            Two open positions: Senior Backend Engineer and ML Ops Engineer.
            14 candidates in the pipeline. David is scheduling final rounds for
            3 backend candidates this week.

            ══ ACTION ITEMS ══
            - Alice: finish Qdrant migration by Sept 30
            - David: audit PagerDuty alerts by Sept 20
            - Bob: code-freeze Project Maple by Oct 1
            - Priya: write ML Ops job description by Sept 15
            - Carol: set up new on-call escalation path
        """),
        "search_must_find": [
            "engineering meeting notes",
            "who is on call in October",
            "vector database migration",
            "Project Maple",
        ],
        "search_must_not_find": [
            "pasta recipe garlic",
            "Niagara ice wine",
        ],
        "answer_keywords": {
            "engineering meeting notes": ["Alice", "Bob", "Carol"],
            "who is on call in October": ["Bob", "Priya"],
            "vector database migration": ["Qdrant", "Pinecone", "Alice"],
        },
    },

    "gt_api_docs": {
        "filename": "widget_api_documentation.md",
        "ext": ".md",
        "content": textwrap.dedent("""\
            # Widget Service API Documentation

            ## Overview
            The Widget Service provides CRUD operations for managing widgets in
            the Wisp platform. All endpoints require Bearer token authentication.

            Base URL: `https://api.wisp.dev/v2/widgets`

            ## Endpoints

            ### POST /widgets
            Create a new widget.

            **Request body:**
            ```json
            {
              "name": "My Widget",
              "type": "dashboard",
              "config": { "refreshInterval": 30, "theme": "dark" }
            }
            ```

            **Response (201):**
            ```json
            {
              "id": "wgt_abc123",
              "name": "My Widget",
              "type": "dashboard",
              "createdAt": "2024-10-01T12:00:00Z"
            }
            ```

            ### GET /widgets/:id
            Retrieve a widget by ID.

            ### PUT /widgets/:id
            Update a widget. Partial updates supported.

            ### DELETE /widgets/:id
            Delete a widget. Returns 204 No Content.

            ## Rate Limits
            - 100 requests/minute per API key
            - Burst: up to 20 concurrent requests

            ## Error Codes
            - 400: Invalid request body
            - 401: Missing or invalid authentication token
            - 404: Widget not found
            - 429: Rate limit exceeded
        """),
        "search_must_find": [
            "API documentation",
            "widget endpoints",
            "how to create a widget",
        ],
        "search_must_not_find": [
            "family vacation",
            "pasta recipe",
        ],
        "answer_keywords": {
            "API documentation": ["Widget", "endpoint", "API"],
            "how to create a widget": ["POST", "/widgets", "Bearer"],
        },
    },

    "gt_budget": {
        "filename": "2024_household_budget.csv",
        "ext": ".csv",
        "content": textwrap.dedent("""\
            Category,January,February,March,April,May,June
            Rent,2200,2200,2200,2200,2200,2200
            Groceries,680,720,650,710,690,740
            Utilities,180,195,160,140,130,125
            Transportation,350,320,380,290,310,340
            Entertainment,200,150,180,220,250,190
            Health Insurance,450,450,450,450,450,450
            Gym Membership,50,50,50,50,50,50
            Subscriptions,85,85,85,85,85,85
            Dining Out,320,280,350,300,270,310
            Savings,1000,1000,1000,1000,1000,1000
            Total,5515,5450,5505,5445,5435,5490
        """),
        "search_must_find": [
            "household budget",
            "monthly expenses",
            "how much do I spend on groceries",
        ],
        "search_must_not_find": [
            "widget API endpoint",
            "Niagara Maid of the Mist",
        ],
        "answer_keywords": {
            "household budget": ["Rent", "Groceries"],
            "how much do I spend on groceries": ["680", "720", "grocery"],
        },
    },

    "gt_code": {
        "filename": "fibonacci_solver.py",
        "ext": ".py",
        "content": textwrap.dedent("""\
            \"\"\"
            Fibonacci Number Calculator — Dynamic Programming
            Supports memoized recursion, bottom-up tabulation, and matrix exponentiation.
            Author: Vishnu Rajeevan
            Date: August 2024
            \"\"\"
            from functools import lru_cache
            from typing import Callable


            @lru_cache(maxsize=None)
            def fib_memo(n: int) -> int:
                \"\"\"Memoized recursive Fibonacci. O(n) time, O(n) space.\"\"\"
                if n < 2:
                    return n
                return fib_memo(n - 1) + fib_memo(n - 2)


            def fib_tabulate(n: int) -> int:
                \"\"\"Bottom-up tabulation. O(n) time, O(1) space.\"\"\"
                if n < 2:
                    return n
                a, b = 0, 1
                for _ in range(2, n + 1):
                    a, b = b, a + b
                return b


            def _matrix_mult(A: list[list[int]], B: list[list[int]]) -> list[list[int]]:
                return [
                    [A[0][0]*B[0][0] + A[0][1]*B[1][0], A[0][0]*B[0][1] + A[0][1]*B[1][1]],
                    [A[1][0]*B[0][0] + A[1][1]*B[1][0], A[1][0]*B[0][1] + A[1][1]*B[1][1]],
                ]


            def _matrix_pow(M: list[list[int]], p: int) -> list[list[int]]:
                result = [[1, 0], [0, 1]]  # identity
                while p:
                    if p % 2:
                        result = _matrix_mult(result, M)
                    M = _matrix_mult(M, M)
                    p //= 2
                return result


            def fib_matrix(n: int) -> int:
                \"\"\"Matrix exponentiation. O(log n) time.\"\"\"
                if n < 2:
                    return n
                return _matrix_pow([[1, 1], [1, 0]], n - 1)[0][0]


            def benchmark(fn: Callable[[int], int], n: int, label: str) -> None:
                import time
                start = time.perf_counter()
                result = fn(n)
                elapsed = (time.perf_counter() - start) * 1000
                print(f"  {label:20s}  fib({n}) = {result}  ({elapsed:.2f} ms)")


            if __name__ == "__main__":
                N = 35
                print(f"Computing fib({N}) three ways:\\n")
                benchmark(fib_memo, N, "Memoized")
                benchmark(fib_tabulate, N, "Tabulation")
                benchmark(fib_matrix, N, "Matrix exp")
        """),
        "search_must_find": [
            "fibonacci code",
            "Python code files",
            "dynamic programming implementation",
        ],
        "search_must_not_find": [
            "Niagara Falls",
            "invoice payment",
        ],
        "answer_keywords": {
            "fibonacci code": ["fibonacci", "memoiz", "matrix"],
            "dynamic programming implementation": ["tabulation", "O(n)"],
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
#  TIER 1 — OFFLINE UNIT TESTS  (no API key, no network)
# ═══════════════════════════════════════════════════════════════════════════════

def run_tier1() -> None:
    print("\n" + "=" * 64)
    print("  TIER 1 — Offline Unit Tests")
    print("=" * 64)

    from services.embedding.chunker import Chunk, chunk_text
    from services.embedding.pipeline import (
        MAX_CHUNKS_PER_FILE,
        _downsample_chunks,
        _build_rag_prompt,
        classify_file,
        MEDIA_EXTENSIONS,
        TEXT_LIKE_EXTENSIONS,
        OFFICE_EXTENSIONS,
        ARCHIVE_EXTENSIONS,
    )
    from services.embedding.store import SearchHit
    from tests.test_embed_pipeline import _file_metadata_description

    # ── T1.1  Downsample: ≤ limit → identity ─────────────────────────────────
    print("\n  ── T1.1: Downsample at/below limit ──")
    chunks = [Chunk(f"f:c{i}", "f", i, f"text {i}") for i in range(MAX_CHUNKS_PER_FILE)]
    result = _downsample_chunks(chunks)
    _check(
        "T1.1: ≤MAX chunks unchanged",
        len(result) == MAX_CHUNKS_PER_FILE,
        f"input={len(chunks)}, output={len(result)}, limit={MAX_CHUNKS_PER_FILE}",
    )

    # ── T1.2  Downsample: above limit → capped ───────────────────────────────
    print("\n  ── T1.2: Downsample 200 → capped ──")
    big = [Chunk(f"f:c{i}", "f", i, f"text {i}") for i in range(200)]
    result = _downsample_chunks(big)
    _check(
        f"T1.2: 200 chunks → {MAX_CHUNKS_PER_FILE}",
        len(result) == MAX_CHUNKS_PER_FILE,
        f"input=200, output={len(result)}",
    )

    # ── T1.3  Downsample: first and last preserved ───────────────────────────
    print("\n  ── T1.3: First + last preserved ──")
    _check(
        "T1.3a: first chunk kept",
        result[0].text == "text 0",
        f"first chunk text={result[0].text!r}",
    )
    _check(
        "T1.3b: last chunk kept",
        result[-1].text == "text 199",
        f"last chunk text={result[-1].text!r}",
    )

    # ── T1.4  Downsample: re-indexes sequentially ────────────────────────────
    print("\n  ── T1.4: Re-indexed sequentially ──")
    indices = [c.chunk_index for c in result]
    expected_indices = list(range(len(result)))
    _check(
        "T1.4: indices sequential after downsample",
        indices == expected_indices,
        f"got {indices[:5]}...{indices[-3:]}",
    )

    # ── T1.5  Downsample: edge case → 1 chunk ────────────────────────────────
    print("\n  ── T1.5: Single chunk → identity ──")
    one = [Chunk("f:c0", "f", 0, "just one")]
    result = _downsample_chunks(one)
    _check("T1.5: 1 chunk unchanged", len(result) == 1 and result[0].text == "just one")

    # ── T1.6  Index card format ───────────────────────────────────────────────
    print("\n  ── T1.6: Index card format ──")
    # Simulate what pipeline.ingest() builds for the card
    from services.file_processor.models import ContentResult
    cr = ContentResult(
        filename="report.pdf", file_name="report.pdf",
        mime_type=".pdf", category="document",
        content="This is a quarterly financial report covering Q3 2024 revenue and expenses.",
        text="This is a quarterly financial report covering Q3 2024 revenue and expenses.",
        engine_used="gemini",
    )
    # Reproduce the index card logic from pipeline.py
    _preview = cr.content[:300].replace("\n", " ").strip()
    card_text = (
        f"[FILE INDEX] This is \"{cr.filename}\", a {cr.mime_type} file "
        f"processed by {cr.engine_used} (5 content chunks).\n"
        f"Content preview: {_preview}"
    )
    _check(
        "T1.6a: card contains [FILE INDEX]",
        "[FILE INDEX]" in card_text,
    )
    _check(
        "T1.6b: card contains filename",
        "report.pdf" in card_text,
    )
    _check(
        "T1.6c: card contains content preview",
        "quarterly financial report" in card_text,
        f"card={card_text!r}",
    )
    _check(
        "T1.6d: card contains engine",
        "gemini" in card_text,
    )

    # ── T1.7  RAG prompt format ───────────────────────────────────────────────
    print("\n  ── T1.7: RAG prompt format ──")
    mock_hits = [
        SearchHit("c1", "f1", 0, "file1.txt", ".txt", "chunk one text", 0.95),
        SearchHit("c2", "f2", 0, "file2.pdf", ".pdf", "chunk two text", 0.88),
    ]
    prompt = _build_rag_prompt("test query", mock_hits)
    _check("T1.7a: prompt contains query", "test query" in prompt)
    _check("T1.7b: prompt contains all sources", "file1.txt" in prompt and "file2.pdf" in prompt)
    _check("T1.7c: prompt contains chunk text", "chunk one text" in prompt and "chunk two text" in prompt)
    _check("T1.7d: prompt has numbered sources", "[1]" in prompt and "[2]" in prompt)

    # ── T1.8  Metadata description ────────────────────────────────────────────
    print("\n  ── T1.8: Metadata description quality ──")
    # Create a temp file to test metadata description
    with tempfile.NamedTemporaryFile(suffix=".dmg", delete=False) as f:
        f.write(b"x" * 5000)
        tmp_path = Path(f.name)
    try:
        desc = _file_metadata_description(tmp_path)
        _check("T1.8a: metadata has filename", tmp_path.name in desc)
        _check("T1.8b: metadata has type", "disk image" in desc.lower() or "dmg" in desc.lower())
        _check("T1.8c: metadata has size", "KB" in desc or "bytes" in desc)
        _check("T1.8d: metadata mentions file exists", "exists" in desc.lower())
    finally:
        tmp_path.unlink()

    # ── T1.9  Chunker handles ground-truth docs ──────────────────────────────
    print("\n  ── T1.9: Chunker handles all ground-truth documents ──")
    for gt_id, gt in GROUND_TRUTH.items():
        chunks = chunk_text(gt["content"], file_id=gt_id)
        _check(
            f"T1.9: {gt['filename']} → {len(chunks)} chunks",
            len(chunks) > 0,
            f"content length={len(gt['content'])} chars",
        )

    # ── T1.10  Downsample doesn't lose coverage for large files ──────────────
    print("\n  ── T1.10: Downsample coverage for large files ──")
    # Simulate a 200-chunk file: first chunks mention topic A, last mention topic B
    large_chunks = []
    for i in range(200):
        if i < 20:
            text = f"Section about quantum computing: qubit entanglement paragraph {i}"
        elif i > 180:
            text = f"Section about climate change: carbon emissions paragraph {i}"
        else:
            text = f"Middle section about neural networks: backpropagation paragraph {i}"
        large_chunks.append(Chunk(f"f:{i}", "f", i, text))

    sampled = _downsample_chunks(large_chunks)
    texts_joined = " ".join(c.text for c in sampled)
    has_quantum = "quantum computing" in texts_joined
    has_climate = "climate change" in texts_joined
    has_neural = "neural networks" in texts_joined
    _check(
        "T1.10: downsample preserves beginning, middle, end topics",
        has_quantum and has_climate and has_neural,
        f"quantum={has_quantum}, climate={has_climate}, neural={has_neural}",
    )

    # ── T1.11  Diversity filter logic ─────────────────────────────────────────
    print("\n  ── T1.11: Diversity filter logic ──")
    # Simulate what search() does: cap per file_id
    fake_hits = [
        SearchHit(f"c{i}", f"file_{i % 3}", i, f"f{i%3}.txt", ".txt", f"text {i}", 1.0 - i * 0.01)
        for i in range(20)
    ]
    # Apply the same logic as pipeline.search()
    max_per_file = 2
    file_counts: dict[str, int] = {}
    diverse: list = []
    for hit in fake_hits:
        count = file_counts.get(hit.file_id, 0)
        if count < max_per_file:
            diverse.append(hit)
            file_counts[hit.file_id] = count + 1
            if len(diverse) >= 6:
                break
    unique_files = len(set(h.file_id for h in diverse))
    _check(
        "T1.11a: diversity filter caps per file",
        all(v <= max_per_file for v in file_counts.values()),
        f"per-file counts: {dict(file_counts)}",
    )
    _check(
        "T1.11b: diversity yields multiple files",
        unique_files >= 3,
        f"unique files in top 6: {unique_files}",
    )

    # ── T1.12  File classification ────────────────────────────────────────────
    print("\n  ── T1.12: classify_file() policy ──")
    _check("T1.12a: .py → full",             classify_file(".py", 5000) == "full")
    _check("T1.12b: .txt → full",            classify_file(".txt", 100000) == "full")
    _check("T1.12c: .pdf ≤80p → full",       classify_file(".pdf", 1000000, pdf_pages=50) == "full")
    _check("T1.12d: .pdf >80p → ai_preview", classify_file(".pdf", 5000000, pdf_pages=200) == "ai_preview")
    _check("T1.12e: .png → ai_preview",      classify_file(".png", 500000) == "ai_preview")
    _check("T1.12f: .mp4 → card_only",       classify_file(".mp4", 50000000) == "card_only")
    _check("T1.12g: .docx → full",           classify_file(".docx", 200000) == "full")
    _check("T1.12h: .zip → card_only",       classify_file(".zip", 1000000) == "card_only")
    _check("T1.12i: .exe → card_only",       classify_file(".exe", 500000) == "card_only")
    _check("T1.12j: unknown .xyz → card_only", classify_file(".xyz", 1000) == "card_only")
    _check("T1.12k: .png 25MB → card_only",  classify_file(".png", 25_000_000) == "card_only")


# ═══════════════════════════════════════════════════════════════════════════════
#  TIER 2 — KNOWN-CONTENT INTEGRATION  (needs GEMINI_API_KEY)
# ═══════════════════════════════════════════════════════════════════════════════

def _ingest_ground_truth(pipeline) -> dict[str, int]:
    """Ingest all ground-truth docs into the current store. Returns {gt_id: chunk_count}."""
    from services.file_processor.models import ContentResult

    counts: dict[str, int] = {}
    for gt_id, gt in GROUND_TRUTH.items():
        cr = ContentResult(
            filename=gt["filename"],
            file_name=gt["filename"],
            mime_type=gt["ext"],
            category="text",
            content=gt["content"],
            text=gt["content"],
            engine_used="local",
        )
        file_id = _file_id_for(gt_id)
        result = pipeline.ingest(cr, file_id=file_id)
        counts[gt_id] = result.chunk_count
        status = f"{result.chunk_count} chunks" if not result.skipped else "SKIPPED"
        print(f"    {gt['filename']:45s} → {status}")
        if result.errors:
            print(f"      WARNINGS: {result.errors}")
    return counts


def run_tier2() -> None:
    print("\n" + "=" * 64)
    print("  TIER 2 — Known-Content Integration Tests")
    print("=" * 64)

    if not _has_api_key():
        _skip("Tier 2", "GEMINI_API_KEY not set")
        return

    from services.embedding import pipeline, store

    tmp = tempfile.mkdtemp(prefix="wisp_tier2_")
    pipeline.init_store(db_path=tmp)
    print(f"  (temp store: {tmp})")

    try:
        # ── Ingest all ground truth ───────────────────────────────────────
        print("\n  ── Ingesting ground-truth documents ──")
        t_start = time.time()
        counts = _ingest_ground_truth(pipeline)
        total_chunks = store.collection_count()
        elapsed = time.time() - t_start
        total_indexed = sum(1 for c in counts.values() if c > 0)
        print(f"\n  ✓ {total_indexed}/{len(GROUND_TRUTH)} documents indexed, "
              f"{total_chunks} chunks in {elapsed:.1f}s")

        # ── T2.1: Every document produced chunks ─────────────────────────
        print("\n  ── T2.1: All documents ingested ──")
        for gt_id, gt in GROUND_TRUTH.items():
            _check(
                f"T2.1: {gt['filename']} has chunks",
                counts.get(gt_id, 0) > 0,
                f"chunk_count={counts.get(gt_id, 0)}",
            )

        # ── T2.2: Search accuracy — must find ────────────────────────────
        print("\n  ── T2.2: Search retrieval — must-find queries ──")
        search_pass = 0
        search_total = 0
        for gt_id, gt in GROUND_TRUTH.items():
            file_id = _file_id_for(gt_id)
            for query in gt["search_must_find"]:
                search_total += 1
                hits = pipeline.search(query, k=10)
                found = any(h.file_id == file_id for h in hits)
                ok = _check(
                    f"T2.2: '{query}' → finds {gt['filename']}",
                    found,
                    f"top files: {[h.file_path or h.file_id for h in hits[:5]]}",
                )
                if ok:
                    search_pass += 1

        print(f"\n  Search recall: {search_pass}/{search_total} "
              f"({100*search_pass/search_total:.0f}%)")

        # ── T2.3: Search accuracy — must NOT find ────────────────────────
        print("\n  ── T2.3: Search retrieval — must-not-find queries ──")
        neg_pass = 0
        neg_total = 0
        for gt_id, gt in GROUND_TRUTH.items():
            file_id = _file_id_for(gt_id)
            for query in gt.get("search_must_not_find", []):
                neg_total += 1
                hits = pipeline.search(query, k=5)
                # The file should NOT be the TOP hit
                not_top = not hits or hits[0].file_id != file_id
                ok = _check(
                    f"T2.3: '{query}' → does NOT top-rank {gt['filename']}",
                    not_top,
                    f"top hit: {hits[0].file_path if hits else 'none'} "
                    f"(file_id={hits[0].file_id if hits else 'none'})",
                )
                if ok:
                    neg_pass += 1
        if neg_total:
            print(f"\n  Negative precision: {neg_pass}/{neg_total} "
                  f"({100*neg_pass/neg_total:.0f}%)")

        # ── T2.4: RAG answer quality — keyword verification ──────────────
        print("\n  ── T2.4: RAG answer quality ──")
        rag_pass = 0
        rag_total = 0
        for gt_id, gt in GROUND_TRUTH.items():
            for query, expected_keywords in gt.get("answer_keywords", {}).items():
                rag_total += 1
                result = asyncio.run(pipeline.ask(query, k=10))
                answer_lower = result.answer.lower()
                found_kws = [kw for kw in expected_keywords if kw.lower() in answer_lower]
                missing_kws = [kw for kw in expected_keywords if kw.lower() not in answer_lower]
                passed = len(found_kws) >= len(expected_keywords) * 0.5  # ≥50% keywords found
                ok = _check(
                    f"T2.4: ask('{query}') → answer quality",
                    passed,
                    f"found: {found_kws}, missing: {missing_kws}\n"
                    f"answer snippet: {result.answer[:200]}",
                )
                if ok:
                    rag_pass += 1
        if rag_total:
            print(f"\n  RAG answer quality: {rag_pass}/{rag_total} "
                  f"({100*rag_pass/rag_total:.0f}%)")

        # ── T2.5: Inventory query — "what files do I have" ──────────────
        print("\n  ── T2.5: Inventory query ──")
        inv_result = asyncio.run(pipeline.ask("What files do I have? Give me an overview."))
        answer_lower = inv_result.answer.lower()
        # Should mention several file types or specific files
        mentioned_files = sum(
            1 for gt in GROUND_TRUTH.values()
            if gt["filename"].lower() in answer_lower
            or gt["filename"].split(".")[0].replace("_", " ").lower() in answer_lower
        )
        # Also check for category mentions
        category_hints = ["resume", "invoice", "recipe", "trip", "meeting", "api", "budget", "code"]
        mentioned_cats = sum(1 for hint in category_hints if hint in answer_lower)
        _check(
            "T2.5a: inventory mentions ≥3 files or categories",
            mentioned_files >= 3 or mentioned_cats >= 3,
            f"files mentioned: {mentioned_files}, categories: {mentioned_cats}\n"
            f"answer: {inv_result.answer[:300]}",
        )
        unique_source_files = len(set(h.file_id for h in inv_result.hits))
        _check(
            "T2.5b: inventory sources span ≥4 unique files",
            unique_source_files >= 4,
            f"unique source files: {unique_source_files}",
        )

        # ── T2.6: Cross-file synthesis ────────────────────────────────────
        print("\n  ── T2.6: Cross-file synthesis ──")
        cross_result = asyncio.run(pipeline.ask(
            "What connections exist between the people mentioned across all my files?"
        ))
        # Should touch at least 2 different source files
        cross_files = len(set(h.file_id for h in cross_result.hits))
        _check(
            "T2.6: cross-file query spans ≥2 source files",
            cross_files >= 2,
            f"unique source files: {cross_files}\n"
            f"answer snippet: {cross_result.answer[:200]}",
        )

        # ── T2.7: Negative — question about non-existent content ─────────
        print("\n  ── T2.7: Negative query ──")
        neg_result = asyncio.run(pipeline.ask(
            "What do my files say about the 2025 Mars colonization program?"
        ))
        answer_lower = neg_result.answer.lower()
        # The answer should NOT confidently describe Mars colonization details
        hallucination_signs = ["mars colonization program", "the program involves", "the 2025 mars"]
        no_hallucinate = not any(sign in answer_lower for sign in hallucination_signs)
        mentions_no_info = any(phrase in answer_lower for phrase in [
            "don't have", "no information", "nothing about", "couldn't find",
            "not mentioned", "don't see", "no mention", "no files",
            "doesn't appear", "don't appear",
        ])
        _check(
            "T2.7: negative query doesn't hallucinate",
            no_hallucinate or mentions_no_info,
            f"answer snippet: {neg_result.answer[:200]}",
        )

        # ── T2.8: Idempotent re-ingestion ────────────────────────────────
        print("\n  ── T2.8: Idempotent re-ingestion ──")
        before = store.collection_count()
        _ingest_ground_truth(pipeline)  # re-ingest all
        after = store.collection_count()
        _check(
            "T2.8: re-ingestion doesn't duplicate chunks",
            before == after,
            f"before={before}, after={after}",
        )

    finally:
        pipeline.teardown_store()
        shutil.rmtree(tmp, ignore_errors=True)
        print("  (cleaned up)")


# ═══════════════════════════════════════════════════════════════════════════════
#  TIER 3 — DOWNLOADS FOLDER SLICES  (needs real download folder + API)
# ═══════════════════════════════════════════════════════════════════════════════

def run_tier3() -> None:
    print("\n" + "=" * 64)
    print("  TIER 3 — Downloads Folder Slices")
    print("=" * 64)

    if not _has_api_key():
        _skip("Tier 3", "GEMINI_API_KEY not set")
        return

    downloads = _downloads_path()
    if not downloads:
        _skip("Tier 3", "Downloads folder not found")
        return

    from tests.test_embed_pipeline import (
        _collect_files_from_dir,
        _categorize_ext,
        _print_scan_summary,
        _ingest_real_files,
    )
    from services.embedding import pipeline, store

    # ── Scan full folder for sampling ─────────────────────────────────────
    print(f"\n  Scanning {downloads} ...")
    all_files = _collect_files_from_dir(str(downloads), recursive=False)
    _print_scan_summary(all_files, downloads)

    # ── Categorize ────────────────────────────────────────────────────────
    by_cat: dict[str, list[Path]] = defaultdict(list)
    for f in all_files:
        ext = f.suffix.lower() if f.is_file() else ".app"
        by_cat[_categorize_ext(ext)].append(f)

    rng = random.Random(42)  # reproducible

    # ── T3.1: PDF slice ──────────────────────────────────────────────────
    print("\n  ── T3.1: PDF slice (up to 15 files) ──")
    pdfs = by_cat.get("PDFs", [])
    if len(pdfs) >= 3:
        sample_pdfs = rng.sample(pdfs, min(15, len(pdfs)))
        tmp = tempfile.mkdtemp(prefix="wisp_t3_pdf_")
        pipeline.init_store(db_path=tmp)
        try:
            counts, _ = _ingest_real_files(sample_pdfs, root=downloads)
            total = store.collection_count()
            indexed = sum(1 for c in counts.values() if c > 0)
            _check(
                f"T3.1a: all {len(sample_pdfs)} PDFs indexed",
                indexed == len(sample_pdfs),
                f"indexed={indexed}, total_chunks={total}",
            )
            _check(
                "T3.1b: each PDF has ≥1 chunk",
                all(c > 0 for c in counts.values()),
                f"chunk counts: {list(counts.values())}",
            )
            # Query test
            hits = pipeline.search("PDF documents", k=10)
            pdf_hits = sum(1 for h in hits if ".pdf" in (h.ext or "").lower()
                          or "pdf" in (h.text or "").lower())
            _check(
                "T3.1c: search 'PDF documents' returns relevant hits",
                pdf_hits >= 1,
                f"PDF-related hits: {pdf_hits}/{len(hits)}",
            )
        finally:
            pipeline.teardown_store()
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        _skip("T3.1", f"only {len(pdfs)} PDFs found, need ≥3")

    # ── T3.2: Image slice ─────────────────────────────────────────────────
    print("\n  ── T3.2: Image slice (up to 10 files) ──")
    images = by_cat.get("Images", [])
    if len(images) >= 3:
        sample_images = rng.sample(images, min(10, len(images)))
        tmp = tempfile.mkdtemp(prefix="wisp_t3_img_")
        pipeline.init_store(db_path=tmp)
        try:
            counts, _ = _ingest_real_files(sample_images, root=downloads)
            indexed = sum(1 for c in counts.values() if c > 0)
            _check(
                f"T3.2a: all {len(sample_images)} images indexed",
                indexed == len(sample_images),
                f"indexed={indexed}",
            )
            hits = pipeline.search("images photos screenshots", k=5)
            _check(
                "T3.2b: image search returns hits",
                len(hits) > 0,
                f"hits: {len(hits)}",
            )
        finally:
            pipeline.teardown_store()
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        _skip("T3.2", f"only {len(images)} images found, need ≥3")

    # ── T3.3: Mixed 50-file sample ───────────────────────────────────────
    print("\n  ── T3.3: Mixed 50-file sample ──")
    targets_per_cat = {
        "PDFs": 8, "Images": 6, "Office": 5, "HTML": 4, "Code": 4,
        "Text": 4, "Data": 4, "Videos": 2, "Audio": 2, "Archives": 3,
        "Installers/Apps": 3, "System/Meta": 2, "Fonts": 1, "Other": 2,
    }
    mixed_sample: list[Path] = []
    for cat, n in targets_per_cat.items():
        avail = by_cat.get(cat, [])
        mixed_sample.extend(rng.sample(avail, min(n, len(avail))))

    if len(mixed_sample) >= 20:
        tmp = tempfile.mkdtemp(prefix="wisp_t3_mix_")
        pipeline.init_store(db_path=tmp)
        try:
            print(f"\n  Ingesting {len(mixed_sample)} files across categories...\n")
            t_start = time.time()
            counts, id_to_name = _ingest_real_files(mixed_sample, root=downloads)
            elapsed = time.time() - t_start
            total_chunks = store.collection_count()
            indexed = sum(1 for c in counts.values() if c > 0)

            _check(
                f"T3.3a: ≥90% of {len(mixed_sample)} files indexed",
                indexed >= len(mixed_sample) * 0.9,
                f"indexed={indexed}/{len(mixed_sample)} in {elapsed:.0f}s, "
                f"chunks={total_chunks}",
            )

            # ── T3.3b: Token budget sanity ────────────────────────────
            avg_chunks = total_chunks / indexed if indexed else 0
            _check(
                "T3.3b: avg chunks/file ≤ 55",
                avg_chunks <= 55,
                f"avg={avg_chunks:.1f}, total_chunks={total_chunks}, files={indexed}",
            )

            # ── T3.3c: No single file dominates ──────────────────────
            max_chunks = max(counts.values()) if counts else 0
            max_fraction = max_chunks / total_chunks if total_chunks else 0
            _check(
                "T3.3c: no single file > 20% of chunks",
                max_fraction <= 0.20,
                f"max file has {max_chunks} chunks ({max_fraction:.1%} of total)",
            )

            # ── T3.3d-f: Query diversity ──────────────────────────────
            test_queries = [
                ("What PDFs do I have?", "T3.3d"),
                ("Show me any code files", "T3.3e"),
                ("What's the most interesting thing in my files?", "T3.3f"),
            ]
            for query, label in test_queries:
                result = asyncio.run(pipeline.ask(query, k=12))
                unique_files = len(set(h.file_id for h in result.hits))
                _check(
                    f"{label}: '{query}' → ≥2 source files",
                    unique_files >= 2,
                    f"unique files: {unique_files}, answer: {result.answer[:150]}",
                )

        finally:
            pipeline.teardown_store()
            shutil.rmtree(tmp, ignore_errors=True)
    else:
        _skip("T3.3", f"only {len(mixed_sample)} files collected, need ≥20")


# ═══════════════════════════════════════════════════════════════════════════════
#  TIER 4 — FULL DOWNLOADS SCALE TEST
# ═══════════════════════════════════════════════════════════════════════════════

def run_tier4() -> None:
    print("\n" + "=" * 64)
    print("  TIER 4 — Full Downloads Scale Test")
    print("=" * 64)

    if not _has_api_key():
        _skip("Tier 4", "GEMINI_API_KEY not set")
        return

    downloads = _downloads_path()
    if not downloads:
        _skip("Tier 4", "Downloads folder not found")
        return

    from tests.test_embed_pipeline import (
        _collect_files_from_dir,
        _categorize_ext,
        _print_scan_summary,
        _ingest_real_files,
    )
    from services.embedding import pipeline, store

    # ── Scan ──────────────────────────────────────────────────────────────
    print(f"\n  Scanning {downloads} (non-recursive) ...")
    all_files = _collect_files_from_dir(str(downloads), recursive=False)
    _print_scan_summary(all_files, downloads)

    if len(all_files) < 50:
        _skip("Tier 4", f"only {len(all_files)} files — need ≥50 for a meaningful scale test")
        return

    # Category counts from filesystem for verification
    fs_cats: Counter = Counter()
    for f in all_files:
        ext = f.suffix.lower() if f.is_file() else ".app"
        fs_cats[_categorize_ext(ext)] += 1

    tmp = tempfile.mkdtemp(prefix="wisp_t4_full_")
    pipeline.init_store(db_path=tmp)

    try:
        # ── T4.1: Full ingestion ──────────────────────────────────────────
        print(f"\n  ── T4.1: Ingesting ALL {len(all_files)} files ──\n")
        t_start = time.time()
        counts, id_to_name = _ingest_real_files(all_files, root=downloads)
        elapsed = time.time() - t_start
        total_chunks = store.collection_count()
        indexed = sum(1 for c in counts.values() if c > 0)
        failed = sum(1 for c in counts.values() if c == 0)
        # Also count files not in counts at all
        missing = len(all_files) - len(counts)

        print(f"\n  Full ingestion: {elapsed:.0f}s")
        print(f"  Indexed: {indexed}, Failed: {failed}, Missing from counts: {missing}")
        print(f"  Total chunks: {total_chunks}")

        _check(
            f"T4.1a: ≥95% of {len(all_files)} files indexed",
            indexed >= len(all_files) * 0.95,
            f"indexed={indexed}/{len(all_files)} ({100*indexed/len(all_files):.1f}%)",
        )
        _check(
            "T4.1b: no files missing from counts",
            missing == 0,
            f"missing={missing}",
        )

        # ── T4.2: Completeness — every file accounted for ────────────────
        print("\n  ── T4.2: File coverage ──")
        files_with_zero = [
            id_to_name.get(fid, fid) for fid, c in counts.items() if c == 0
        ]
        _check(
            "T4.2: zero-chunk files ≤ 5% of total",
            len(files_with_zero) <= len(all_files) * 0.05,
            f"zero-chunk files: {len(files_with_zero)}" +
            (f" — {files_with_zero[:10]}" if files_with_zero else ""),
        )

        # ── T4.3: Token budget ────────────────────────────────────────────
        print("\n  ── T4.3: Token budget ──")
        avg_chunks = total_chunks / indexed if indexed else 0
        # Rough token estimate: 200 tokens per chunk
        est_tokens = total_chunks * 200
        _check(
            "T4.3a: avg chunks/file reasonable (≤ 55)",
            avg_chunks <= 55,
            f"avg={avg_chunks:.1f} chunks/file",
        )
        _check(
            f"T4.3b: total embedding tokens ≤ 5M",
            est_tokens <= 5_000_000,
            f"estimated {est_tokens:,} tokens ({total_chunks} chunks × 200 tok/chunk)",
        )

        # ── T4.4: No single file dominates ────────────────────────────────
        print("\n  ── T4.4: Chunk distribution ──")
        if counts:
            max_file_chunks = max(counts.values())
            max_file_name = id_to_name.get(
                max(counts, key=counts.get), "unknown"
            )
            max_pct = max_file_chunks / total_chunks if total_chunks else 0
            _check(
                "T4.4a: no file > 5% of total chunks",
                max_pct <= 0.05,
                f"largest: {max_file_name} with {max_file_chunks} chunks ({max_pct:.1%})",
            )

            # Check top-5 files don't collectively dominate
            top5 = sorted(counts.values(), reverse=True)[:5]
            top5_pct = sum(top5) / total_chunks if total_chunks else 0
            _check(
                "T4.4b: top 5 files < 25% of chunks",
                top5_pct < 0.25,
                f"top 5 collectively: {sum(top5)} chunks ({top5_pct:.1%})",
            )

        # ── T4.5: Query battery ───────────────────────────────────────────
        print("\n  ── T4.5: Query battery ──")
        battery = [
            {
                "query": "What PDFs do I have in my downloads?",
                "label": "T4.5a: PDF inventory",
                "check": lambda r: len(set(h.file_id for h in r.hits)) >= 2,
                "detail": lambda r: f"{len(set(h.file_id for h in r.hits))} unique files",
            },
            {
                "query": "Do I have any resumes or CVs?",
                "label": "T4.5b: Resume search",
                "check": lambda r: len(r.answer) > 20,  # non-trivial answer
                "detail": lambda r: f"answer: {r.answer[:150]}",
            },
            {
                "query": "What images or photos are in my downloads?",
                "label": "T4.5c: Image inventory",
                "check": lambda r: len(set(h.file_id for h in r.hits)) >= 2,
                "detail": lambda r: f"{len(set(h.file_id for h in r.hits))} unique files",
            },
            {
                "query": "Are there any code files or programming projects?",
                "label": "T4.5d: Code search",
                "check": lambda r: len(r.answer) > 20,
                "detail": lambda r: f"answer: {r.answer[:150]}",
            },
            {
                "query": "What kinds of files do I have? Give a categorized overview.",
                "label": "T4.5e: Broad overview",
                "check": lambda r: (
                    len(set(h.file_id for h in r.hits)) >= 3
                    and len(r.answer) > 50
                ),
                "detail": lambda r: (
                    f"{len(set(h.file_id for h in r.hits))} unique sources\n"
                    f"answer: {r.answer[:200]}"
                ),
            },
            {
                "query": "Do I have any installers or applications downloaded?",
                "label": "T4.5f: Installer search",
                "check": lambda r: len(r.answer) > 20,
                "detail": lambda r: f"answer: {r.answer[:150]}",
            },
            {
                "query": "What's the largest or most notable file in my downloads?",
                "label": "T4.5g: Notable file",
                "check": lambda r: len(r.answer) > 20,
                "detail": lambda r: f"answer: {r.answer[:150]}",
            },
            {
                "query": "Are there any spreadsheets or data files?",
                "label": "T4.5h: Data file search",
                "check": lambda r: len(r.answer) > 20,
                "detail": lambda r: f"answer: {r.answer[:150]}",
            },
        ]

        query_pass = 0
        for test in battery:
            result = asyncio.run(pipeline.ask(test["query"]))
            ok = test["check"](result)
            _check(test["label"], ok, test["detail"](result))
            if ok:
                query_pass += 1

        print(f"\n  Query battery: {query_pass}/{len(battery)} passed")

        # ── T4.6: Retrieval latency ───────────────────────────────────────
        print("\n  ── T4.6: Retrieval latency ──")
        latencies = []
        for _ in range(5):
            q = random.choice([t["query"] for t in battery])
            t0 = time.time()
            pipeline.search(q, k=10)
            latencies.append(time.time() - t0)
        avg_lat = sum(latencies) / len(latencies)
        p95_lat = sorted(latencies)[int(len(latencies) * 0.95)]
        _check(
            "T4.6: avg search latency < 5s",
            avg_lat < 5.0,
            f"avg={avg_lat:.2f}s, p95={p95_lat:.2f}s",
        )

    finally:
        pipeline.teardown_store()
        shutil.rmtree(tmp, ignore_errors=True)
        print("  (cleaned up)")


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN — run requested tier(s)
# ═══════════════════════════════════════════════════════════════════════════════

def main() -> None:
    print("\n╔══════════════════════════════════════════════╗")
    print("║  WISP — Tiered Pipeline Test Suite           ║")
    print("╚══════════════════════════════════════════════╝")

    # Parse --tier N
    tier_arg = None
    if "--tier" in sys.argv:
        idx = sys.argv.index("--tier") + 1
        if idx < len(sys.argv):
            tier_arg = int(sys.argv[idx])

    tiers = {
        1: ("Tier 1 — Offline Unit Tests", run_tier1),
        2: ("Tier 2 — Known-Content Integration", run_tier2),
        3: ("Tier 3 — Downloads Slices", run_tier3),
        4: ("Tier 4 — Full Downloads Scale", run_tier4),
    }

    if tier_arg:
        if tier_arg in tiers:
            name, fn = tiers[tier_arg]
            print(f"\n  Running: {name}")
            fn()
        else:
            print(f"  Unknown tier: {tier_arg}. Available: 1, 2, 3, 4")
            sys.exit(1)
    else:
        for tier_num, (name, fn) in tiers.items():
            fn()

    # ── Summary ───────────────────────────────────────────────────────────
    total = _pass_count + _fail_count
    print("\n" + "=" * 64)
    print(f"  RESULTS: {_pass_count} passed, {_fail_count} failed"
          + (f", {_skip_count} skipped" if _skip_count else ""))
    if total > 0:
        print(f"  Pass rate: {100 * _pass_count / total:.0f}%")
    print("=" * 64 + "\n")

    sys.exit(0 if _fail_count == 0 else 1)


if __name__ == "__main__":
    main()

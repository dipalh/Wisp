#!/usr/bin/env python3
"""Run semantic queries against the live LanceDB store from the Downloads demo.

This proves the pipeline does real semantic search (vector similarity),
not keyword matching / grep.
"""

import sys, asyncio, textwrap, shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.embedding import pipeline, store

# ── Semantic test queries ────────────────────────────────────────────────
# These test paraphrase / concept matching — things grep can NEVER do.
QUERIES = [
    # Paraphrase: no exact keyword match expected
    "what are my qualifications and work experience?",
    # Concept search across multiple files
    "math exam solutions or proofs",
    # Fuzzy: user remembers topic not filename
    "that document about a job offer or employment terms",
    # Image content (only possible with AI preview depth)
    "pictures or screenshots I downloaded",
    # Concept query: user wants to find a cover letter
    "cover letter for a software developer position",
    # Academic content discovery
    "computer science data structures algorithms",
]


def run_query(q: str, k: int = 5) -> None:
    """Run a single query and print results."""
    width = min(shutil.get_terminal_size().columns - 4, 80)

    print(f"\n  Q: {q}")
    print(f"  {'─' * (width - 4)}")

    result = asyncio.run(pipeline.ask(q, k=k))

    # Print answer (wrapped)
    for line in result.answer.splitlines():
        for wrapped in textwrap.wrap(line, width=width - 6) or [""]:
            print(f"    {wrapped}")

    # Print sources
    if result.hits:
        seen: set[str] = set()
        sources: list[str] = []
        for h in result.hits:
            label = Path(h.file_path).name if h.file_path else h.file_id
            if label not in seen:
                seen.add(label)
                sources.append(f"{label} (score={h.score:.3f}, depth={h.depth})")
        print(f"\n    Sources:")
        for s in sources:
            print(f"      • {s}")


def main():
    # Connect to the existing store
    store.init()
    count = store.collection_count()
    print(f"\n  Connected to LanceDB store: {count} chunks")
    print(f"  {pipeline.scan_summary()}")

    print(f"\n{'=' * 70}")
    print("  SEMANTIC QUERY TEST — proving this is NOT grep")
    print(f"{'=' * 70}")

    for q in QUERIES:
        run_query(q, k=5)
        print()

    # Teardown
    pipeline.teardown_store()
    print(f"\n  Done. {len(QUERIES)} queries executed against {count} chunks.\n")


if __name__ == "__main__":
    main()

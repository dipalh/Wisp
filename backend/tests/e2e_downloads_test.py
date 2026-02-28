"""
End-to-end test: ingest a representative sample from the downloads folder,
then ask questions and evaluate the responses.
"""
import sys
import os
import random
import hashlib
import asyncio
import time
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from dotenv import load_dotenv
_env = Path(__file__).parent.parent / ".env"
if _env.exists():
    load_dotenv(dotenv_path=_env, override=False)

from tests.test_embed_pipeline import (
    _collect_files_from_dir,
    _categorize_ext,
    _file_metadata_description,
    _print_scan_summary,
    _ingest_real_files,
    MAX_GEMINI_FILE_SIZE_MB,
)
from services.embedding import pipeline, store
from services.file_processor.dispatcher import extract as dispatch_extract


def select_sample(files: list[Path], n_per_cat: dict[str, int], seed: int = 42) -> list[Path]:
    """Pick a representative sample covering all file categories."""
    by_cat: dict[str, list[Path]] = defaultdict(list)
    for f in files:
        ext = f.suffix.lower() if f.is_file() else ".app"
        by_cat[_categorize_ext(ext)].append(f)

    rng = random.Random(seed)
    sample = []
    for cat, n in n_per_cat.items():
        avail = by_cat.get(cat, [])
        sample.extend(rng.sample(avail, min(n, len(avail))))

    print(f"\n  Selected {len(sample)} files across {len(n_per_cat)} categories:")
    for cat in sorted(n_per_cat.keys()):
        avail = len(by_cat.get(cat, []))
        picked = min(n_per_cat[cat], avail)
        print(f"    {cat:18s}  {picked:>2} / {avail}")
    return sample


def run_e2e():
    print("\n" + "=" * 64)
    print("  WISP — End-to-End Downloads Folder Test")
    print("=" * 64)

    # 1. Scan
    downloads = Path("../downloads").resolve()
    print(f"\n  Scanning {downloads} ...")
    all_files = _collect_files_from_dir(str(downloads), recursive=False)
    _print_scan_summary(all_files, downloads)

    # 2. Sample
    targets = {
        "PDFs": 4, "Images": 3, "Office": 3, "HTML": 2,
        "Code": 2, "Text": 2, "Data": 2, "Videos": 1, "Audio": 1,
        "Archives": 2, "Installers/Apps": 2, "System/Meta": 2,
        "Other": 2,
    }
    sample = select_sample(all_files, targets)

    # 3. Init store
    import tempfile
    tmp = tempfile.mkdtemp(prefix="wisp_e2e_")
    pipeline.init_store(db_path=tmp)

    try:
        # 4. Ingest
        print(f"\n  Ingesting {len(sample)} files...\n")
        counts, id_to_name = _ingest_real_files(sample, root=downloads)
        total_chunks = store.collection_count()
        total_indexed = sum(1 for c in counts.values() if c > 0)
        print(f"\n  ✓ {total_indexed} files indexed, {total_chunks} chunks")

        # 5. Run test queries
        test_queries = [
            "What PDFs do I have in my downloads?",
            "Do I have any resumes or CVs?",
            "What kinds of files are in my downloads folder?",
            "Are there any images? What do they show?",
            "Do I have any installers or applications downloaded?",
            "What's the most interesting thing in my downloads?",
        ]

        print("\n" + "=" * 64)
        print("  QUERY EVALUATION")
        print("=" * 64)

        for q in test_queries:
            print(f"\n  Q: {q}")
            print("  " + "-" * 60)
            result = asyncio.run(pipeline.ask(q, k=8))
            print(f"  A: {result.answer[:500]}")
            sources = []
            seen = set()
            for h in result.hits:
                label = id_to_name.get(h.file_id, h.file_path or h.file_id)
                if label not in seen:
                    seen.add(label)
                    sources.append(label)
            print(f"  Sources: {', '.join(sources[:5])}")
            print()

    finally:
        pipeline.teardown_store()
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
        print("  (cleaned up)")


if __name__ == "__main__":
    run_e2e()

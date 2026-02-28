#!/usr/bin/env python3
"""Quick demo: ingest a manageable sample from Downloads, then interactive query."""

import sys, os, hashlib, time, shutil, textwrap, asyncio, random
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── Sample diverse files from a directory ────────────────────────────────
def sample_files(root: Path, target: int = 120) -> list[Path]:
    """Pick a diverse sample: some of each extension type."""
    by_ext: dict[str, list[Path]] = {}
    for f in root.iterdir():
        if not f.is_file() or f.name.startswith("."):
            continue
        ext = f.suffix.lower() or ".noext"
        by_ext.setdefault(ext, []).append(f)

    # Prioritise variety: take up to N from each ext, round-robin
    selected: list[Path] = []
    # Sort extensions by count descending so we prioritise common types
    exts_sorted = sorted(by_ext.keys(), key=lambda e: -len(by_ext[e]))
    per_ext = max(2, target // len(exts_sorted)) if exts_sorted else target

    for ext in exts_sorted:
        pool = by_ext[ext]
        random.shuffle(pool)
        take = min(len(pool), per_ext)
        selected.extend(pool[:take])
        if len(selected) >= target:
            break

    # If we're under target, fill with remaining files
    if len(selected) < target:
        used = set(selected)
        for ext in exts_sorted:
            for f in by_ext[ext]:
                if f not in used:
                    selected.append(f)
                    used.add(f)
                    if len(selected) >= target:
                        break
            if len(selected) >= target:
                break

    return selected[:target]


def main():
    from services.embedding import pipeline, store

    dl = Path.home() / "Downloads"
    if not dl.is_dir():
        print("~/Downloads not found")
        return

    target = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    files = sample_files(dl, target)

    # Print type breakdown
    by_ext: dict[str, int] = {}
    for f in files:
        ext = f.suffix.lower() or ".noext"
        by_ext[ext] = by_ext.get(ext, 0) + 1
    print(f"\n  Sampled {len(files)} files from ~/Downloads")
    print(f"  Types: {', '.join(f'{ext}({n})' for ext, n in sorted(by_ext.items(), key=lambda x: -x[1]))}")

    # Create temp store
    tmp = Path(os.environ.get("TMPDIR", "/tmp")) / f"wisp_demo_{os.getpid()}"
    tmp.mkdir(parents=True, exist_ok=True)
    os.environ["WISP_LANCE_PATH"] = str(tmp / "demo.lance")
    pipeline.init_store()

    id_to_name: dict[str, str] = {}
    preview_count = 0
    error_count = 0
    start = time.time()
    total = len(files)

    try:
        for idx, fpath in enumerate(files, 1):
            display = fpath.name
            fid = hashlib.sha256(str(fpath).encode()).hexdigest()[:16]
            id_to_name[fid] = display

            elapsed = time.time() - start
            if idx > 3 and elapsed > 0:
                rate = idx / elapsed
                remaining = (total - idx) / rate
                eta = f"  ~{remaining:.0f}s left" if remaining > 5 else ""
            else:
                eta = ""

            short = display[:55] if len(display) <= 55 else "..." + display[-52:]
            print(f"  [{idx:>4}/{total}] {short}", end="", flush=True)

            try:
                result = asyncio.run(pipeline.ingest_file(fpath, fid))
                if result.skipped:
                    print(f"  → cached{eta}")
                elif result.depth != "deep":
                    preview_count += 1
                    print(f"  → {result.depth} [{result.engine}]{eta}")
                else:
                    print(f"  → {result.chunk_count} chunks [{result.engine}]{eta}")
            except Exception as exc:
                print(f"  → FAILED: {str(exc)[:60]}{eta}")
                error_count += 1

        elapsed = time.time() - start
        total_chunks = store.collection_count()
        print(f"\n  ✓ Ingested {total} files in {elapsed:.1f}s — {total_chunks} chunks total")
        if error_count:
            print(f"  ! {error_count} file(s) failed")
        print(f"\n  {pipeline.scan_summary()}")
        print(f"\n  Ask anything about your files.  Type 'quit' to exit.\n")

        # ── Interactive query loop ────────────────────────────────────
        while True:
            try:
                query = input("  wisp> ").strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if not query or query.lower() in ("quit", "exit", "q"):
                break

            print("  thinking...\n")
            result = asyncio.run(pipeline.ask(query, k=8))

            width = min(shutil.get_terminal_size().columns - 6, 78)
            border = "─" * (width - 2)
            print(f"  ┌{border}┐")
            for line in result.answer.splitlines():
                for wrapped in textwrap.wrap(line, width=width - 4) or [""]:
                    pad = " " * (width - 2 - len(wrapped))
                    print(f"  │ {wrapped}{pad}│")
            print(f"  └{border}┘")

            if result.hits:
                seen: set[str] = set()
                sources: list[str] = []
                for h in result.hits:
                    label = id_to_name.get(h.file_id, h.file_path or h.file_id)
                    if label not in seen:
                        seen.add(label)
                        sources.append(label)
                print(f"  sources: {', '.join(sources)}")
            print()

    finally:
        pipeline.teardown_store()
        shutil.rmtree(tmp, ignore_errors=True)
        print("  (cleaned up)")


if __name__ == "__main__":
    main()

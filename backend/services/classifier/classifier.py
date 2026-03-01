"""
Per-file classifier for Wisp.

Flow per file
-------------
1. Read this file's card text from LanceDB (already indexed).
2. Query vector DB for top ~20 semantically similar files (neighbors).
3. Send the file summary + neighbor context to Gemini.
4. Gemini returns {category, tags, confidence}.
5. Move the file into base_dir/<category>/ if confidence >= threshold,
   otherwise base_dir/Unsorted/.
6. Record an APPLIED MOVE action for undo support.

Public API
----------
  classify_file(fp, file_id, base_dir) -> ClassificationResult | None
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .models import CATEGORIES, CONFIDENCE_THRESHOLD, ClassificationResult


async def classify_file(
    fp: Path,
    file_id: str,
    base_dir: Path,
) -> ClassificationResult | None:
    """Classify a single file and move it into the appropriate category folder.

    Args:
        fp:       Absolute path to the file on disk.
        file_id:  The file's LanceDB identifier (SHA256[:16] of the path).
        base_dir: Root directory — category subfolders are created here.

    Returns:
        The ClassificationResult from Gemini, or None if classification failed.
    """
    from services.embedding import pipeline, store as vec_store
    from ai.generate import generate_structured
    from services.actions import Action, ActionType, ActionStatus, add as add_action

    # 1. Get the file's card text from LanceDB (chunk_index == -1 row).
    #    Fall back to the bare filename if the card isn't found.
    file_records = vec_store.list_files()
    card_text = next(
        (r["text"] for r in file_records if r["file_id"] == file_id),
        fp.name,
    )

    # 2. Find top-20 neighbors — similar files already in the collection.
    #    Request k=21 so we can drop the file itself if it shows up.
    hits = await pipeline.search(card_text, k=21)
    neighbors = [h for h in hits if h.file_id != file_id][:20]

    # 3. Build the classification prompt.
    neighbors_block = "\n".join(
        f"- {Path(h.file_path).name} ({h.ext}): {h.text[:200]}"
        for h in neighbors
    ) or "(no indexed neighbors yet)"

    prompt = (
        f"You are a file classifier. Classify the target file into exactly one category.\n\n"
        f"Target: {fp.name} ({fp.suffix})\n"
        f"Summary: {card_text[:500]}\n\n"
        f"Similar files already in this user's collection:\n"
        f"{neighbors_block}\n\n"
        f"Available categories: {', '.join(CATEGORIES[:-1])}\n"
        f"Use 'Unsorted' only when the file genuinely doesn't fit any category.\n\n"
        f"Return JSON: {{\"category\": \"...\", \"tags\": [\"...\"], \"confidence\": 0.0}}"
    )

    # 4. Call Gemini with structured output.
    result = await generate_structured(prompt, ClassificationResult)

    # 5. Determine the actual destination: high-confidence → named category, else Unsorted.
    category = result.category if result.confidence >= CONFIDENCE_THRESHOLD else "Unsorted"
    # Guard against Gemini returning an unexpected category string.
    if category not in CATEGORIES:
        category = "Unsorted"

    target_dir = base_dir / category
    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / fp.name
    if target_path.exists():
        # Avoid overwriting an existing file by appending the file_id fragment.
        target_path = target_dir / f"{fp.stem}_{file_id[:6]}{fp.suffix}"

    # 6. Move the file.
    shutil.move(str(fp), str(target_path))

    # 7. Record the move in the Action Engine so the user can undo it.
    add_action(Action(
        type=ActionType.MOVE,
        label=f"Auto-classify '{fp.name}' → {category}/",
        targets=[str(fp)],
        before_state={"path": str(fp)},
        after_state={"path": str(target_path)},
        status=ActionStatus.APPLIED,
    ))

    return result

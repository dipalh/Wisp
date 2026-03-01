"""
Proposal Engine — generates action proposals from RAG search hits.

Walks the files that appeared in the top search hits, scores each one
with the Heuristics Engine, and surfaces any that cross the junk
threshold as PROPOSED actions in the Action Store.

Only MOVE-to-quarantine proposals are generated automatically.
Hard DELETE is never auto-proposed — the user must trigger that
explicitly.  This keeps the agent safe by default.

Public API
----------
  propose_from_hits(hits)       -> list[dict]
  quarantine_dir_for(file_path) -> Path
"""
from __future__ import annotations

import time
from pathlib import Path

import services.actions as action_store
from services.actions.models import Action, ActionStatus, ActionType
from services.heuristics import score_file

# Files below this junk_score are not proposed for cleanup.
PROPOSAL_THRESHOLD = 0.35


def quarantine_dir_for(file_path: Path) -> Path:
    """Return the quarantine directory appropriate for *file_path*.

    Priority:
      1. If any root is registered AND the file is under that root,
         use  ``{root}/.wisp_quarantine/``.
      2. Otherwise (open mode or file outside all roots):
         use  ``{file_path.parent}/.wisp_quarantine/``.
    """
    from services.roots import get_roots
    for root_str in get_roots():
        root = Path(root_str)
        try:
            if file_path.is_relative_to(root):
                return root / ".wisp_quarantine"
        except ValueError:
            pass
    return file_path.parent / ".wisp_quarantine"


def propose_from_hits(hits) -> list[dict]:
    """Score files from search hits and return proposals for junk files.

    Each unique file in *hits* (by file_path) is scored with
    ``score_file()``.  Files at or above ``PROPOSAL_THRESHOLD`` get a
    MOVE-to-quarantine proposal recorded in the Action Store.

    Skips:
      - Hits with missing / empty file_path
      - Files that do not exist on disk (stale index entries)
      - Duplicate file_path entries in hits (only first hit wins)

    Args:
        hits: Iterable of SearchHit objects from pipeline.search() / ask().

    Returns:
        List of proposal dicts, each containing:
          action_id, file_path, file_id, action_type, destination,
          junk_score, reasons, recommended_action, label
    """
    seen_paths: set[str] = set()
    proposals: list[dict] = []

    for hit in hits:
        file_path_str = hit.file_path or ""
        if not file_path_str or file_path_str in seen_paths:
            continue
        seen_paths.add(file_path_str)

        fp = Path(file_path_str)
        if not fp.exists():
            continue

        scored = score_file(fp)
        if scored["junk_score"] < PROPOSAL_THRESHOLD:
            continue

        # Build the quarantine destination path, handling name collisions.
        q_dir = quarantine_dir_for(fp)
        dest  = q_dir / fp.name
        if dest.exists():
            dest = q_dir / f"{fp.stem}_{int(time.time())}{fp.suffix}"

        label = (
            f"Quarantine {fp.name} "
            f"(junk score: {scored['junk_score']:.0%}, "
            f"{', '.join(scored['reasons'][:2])})"
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

        proposals.append({
            "action_id":          action.id,
            "file_path":          str(fp),
            "file_id":            hit.file_id,
            "action_type":        "MOVE",
            "destination":        str(dest),
            "junk_score":         scored["junk_score"],
            "reasons":            scored["reasons"],
            "recommended_action": scored["recommended_action"],
            "label":              label,
        })

    return proposals

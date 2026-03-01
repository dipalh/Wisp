import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from services.actions import Action, ActionStatus, ActionType
from services.actions import add as add_action
from services.job_db import create_job, set_status, update_progress
from services.organizer.models import DirectorySuggestions
from services.organizer.suggester import suggest_directories

router = APIRouter()


class MappingItem(BaseModel):
    original_path: str
    suggested_path: str


class ApplyRequest(BaseModel):
    mappings: list[MappingItem]


@router.post("/apply", summary="Apply an organization proposal")
async def apply_proposal(body: ApplyRequest, background_tasks: BackgroundTasks):
    """Move files according to the chosen proposal mappings."""
    if not body.mappings:
        raise HTTPException(status_code=400, detail="mappings must not be empty")
    job_id = uuid.uuid4().hex
    create_job(job_id, "organize")
    background_tasks.add_task(_run_organize, job_id, body.mappings)
    return {"job_id": job_id}


def _run_organize(job_id: str, mappings: list[MappingItem]) -> None:
    total = len(mappings)
    moved = 0
    failed = 0
    set_status(job_id, "running")
    update_progress(job_id, 0, total, "Starting file moves\u2026")
    for i, m in enumerate(mappings):
        src = Path(m.original_path)
        dst = Path(m.suggested_path)
        update_progress(job_id, i, total, f"Moving: {src.name}")
        try:
            dst.parent.mkdir(parents=True, exist_ok=True)
            src.rename(dst)
            moved += 1
        except OSError:
            try:
                shutil.copy2(str(src), str(dst))
                src.unlink()
                moved += 1
            except Exception:
                failed += 1
        update_progress(job_id, i + 1, total, f"Moved: {src.name}")
    msg = f"Done \u2014 {moved}/{total} files moved" + (f", {failed} failed" if failed else "")
    set_status(job_id, "success" if failed == 0 else "failed", msg)


@router.get(
    "/suggestions",
    response_model=DirectorySuggestions,
    summary="Propose directory structures from indexed files",
)
async def get_suggestions():
    """
    Read all indexed files from LanceDB and return 2-3 directory organization proposals.

    Each proposal includes:
    - **name**: a short label for the scheme
    - **rationale**: why this structure makes sense
    - **folder_tree**: the directory paths that make it up
    - **mappings**: per-file current → suggested path

    Also returns a **recommendation** indicating the best proposal.

    Side effect: creates PROPOSED MOVE actions in the Action Engine for the first proposal's
    mappings so the user can inspect or undo them later.
    """
    try:
        suggestions = await suggest_directories()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Organizer failed: {e}")

    # Register PROPOSED MOVE actions for the first (best) proposal
    best = suggestions.proposals[0] if suggestions.proposals else None
    if best:
        for m in best.mappings:
            add_action(Action(
                type=ActionType.MOVE,
                label=f"Move '{Path(m.original_path).name}' → {m.suggested_path}",
                targets=[m.original_path],
                before_state={"path": m.original_path},
                after_state={"path": m.suggested_path},
                status=ActionStatus.PROPOSED,
            ))

    return suggestions

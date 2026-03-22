from pathlib import Path
import shutil

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.organizer.batch_state import apply_batch, create_batch, has_batch, undo_batch
from services.organizer.models import DirectorySuggestions
from services.organizer.proposal_state import accept as accept_proposal
from services.organizer.proposal_state import is_accepted
from services.organizer.proposal_state import mappings_for
from services.organizer.suggester import suggest_directories

router = APIRouter()


class _MappingPayload(BaseModel):
    original_path: str
    suggested_path: str


class _AcceptRequest(BaseModel):
    mappings: list[_MappingPayload] = Field(default_factory=list)


class _ProposalsRequest(BaseModel):
    mock_mode: bool = False
    tool_budget: int | None = None


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

    This endpoint is proposal-only and does not mutate filesystem/action state.
    """
    try:
        suggestions = await suggest_directories()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Organizer failed: {e}")

    return suggestions


@router.post(
    "/proposals",
    summary="Generate organize proposal strategies",
)
async def post_proposals(payload: _ProposalsRequest):
    try:
        suggestions = await suggest_directories(
            mock_mode=payload.mock_mode,
            tool_budget=payload.tool_budget,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Organizer failed: {e}")

    return {
        "ok": True,
        "strategies": [p.model_dump() for p in suggestions.proposals],
        "recommendation": suggestions.recommendation,
        "degraded": "degraded" in suggestions.recommendation.lower(),
    }


@router.post(
    "/proposals/{proposal_id}/accept",
    summary="Accept an organize proposal so it can be applied",
)
async def accept_organize_proposal(proposal_id: str, payload: _AcceptRequest | None = None):
    mappings = []
    if payload is not None:
        mappings = [m.model_dump() for m in payload.mappings]
    accept_proposal(proposal_id, mappings=mappings)
    batch_id = create_batch(proposal_id, mappings)
    return {"ok": True, "proposal_id": proposal_id, "accepted": True, "batch_id": batch_id}


@router.post(
    "/proposals/{proposal_id}/apply",
    summary="Apply an accepted organize proposal",
)
async def apply_organize_proposal(proposal_id: str):
    if not is_accepted(proposal_id):
        raise HTTPException(
            status_code=409,
            detail={
                "code": "ORGANIZE_ACCEPT_REQUIRED",
                "message": "Proposal must be accepted before apply",
            },
        )
    for mapping in mappings_for(proposal_id):
        dst_path = mapping.get("suggested_path", "")
        if dst_path and Path(dst_path).exists():
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "DESTINATION_COLLISION",
                    "message": f"destination already exists: {dst_path}",
                },
            )
    for mapping in mappings_for(proposal_id):
        src_path = mapping.get("original_path", "")
        dst_path = mapping.get("suggested_path", "")
        if not src_path or not dst_path:
            continue
        src = Path(src_path)
        dst = Path(dst_path)
        if not src.exists():
            raise HTTPException(
                status_code=422,
                detail={"code": "SOURCE_MISSING", "message": f"source missing: {src_path}"},
            )
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    return {"ok": True, "proposal_id": proposal_id, "applied": True}


@router.post(
    "/proposals/{proposal_id}/undo",
    summary="Undo an applied organize proposal batch",
)
async def undo_organize_proposal(proposal_id: str):
    for mapping in mappings_for(proposal_id):
        original = mapping.get("original_path", "")
        moved = mapping.get("suggested_path", "")
        if not original or not moved:
            continue
        src = Path(moved)
        dst = Path(original)
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    return {"ok": True, "proposal_id": proposal_id, "undone": True}


@router.post(
    "/batches/{batch_id}/apply",
    summary="Apply an organize action batch",
)
async def apply_organize_batch(batch_id: str):
    if not has_batch(batch_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "BATCH_NOT_FOUND", "message": f"unknown batch_id: {batch_id}"},
        )
    try:
        apply_batch(batch_id)
    except FileExistsError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "DESTINATION_COLLISION", "message": f"destination already exists: {exc}"},
        )
    return {"ok": True, "batch_id": batch_id, "applied": True}


@router.post(
    "/batches/{batch_id}/undo",
    summary="Undo an organize action batch",
)
async def undo_organize_batch(batch_id: str):
    if not has_batch(batch_id):
        raise HTTPException(
            status_code=404,
            detail={"code": "BATCH_NOT_FOUND", "message": f"unknown batch_id: {batch_id}"},
        )
    undo_batch(batch_id)
    return {"ok": True, "batch_id": batch_id, "undone": True}

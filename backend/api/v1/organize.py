from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import services.actions as action_store
from services.actions.batch_executor import apply_batch as apply_action_batch
from services.actions.batch_executor import undo_batch as undo_action_batch
from services.actions.models import Action, ActionStatus, ActionType
from services.organizer.models import DirectorySuggestions
from services.organizer.proposal_state import accept as accept_proposal
from services.organizer.proposal_state import batch_for
from services.organizer.proposal_state import is_accepted
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
    actions: list[Action] = []
    for mapping in mappings:
        src_path = mapping.get("original_path", "")
        dst_path = mapping.get("suggested_path", "")
        if not src_path or not dst_path:
            continue
        action = Action(
            type=ActionType.MOVE,
            label=f"Organize {src_path} -> {dst_path}",
            targets=[src_path],
            before_state={"path": src_path},
            after_state={"path": dst_path},
            proposal_id=proposal_id,
            source="organizer",
            actor="organizer",
            status=ActionStatus.ACCEPTED,
        )
        action_store.add(action)
        actions.append(action)

    if actions:
        batch = action_store.create_batch(
            [action.id for action in actions],
            proposal_id=proposal_id,
            actor="organizer",
        )
        batch_id = batch["batch_id"]
        for action in actions:
            action.batch_id = batch_id
            action_store.add(action)
    else:
        batch_id = f"noop_{proposal_id}"

    accept_proposal(proposal_id, mappings=mappings, batch_id=batch_id)
    return {"ok": True, "proposal_id": proposal_id, "accepted": True, "batch_id": batch_id}


def _raise_from_batch_failure(result: dict) -> None:
    details = result.get("details") or []
    failure = next((detail for detail in details if detail.get("status") == ActionStatus.FAILED.value), None)
    if failure is None:
        return
    code = failure.get("code", "BATCH_APPLY_FAILED")
    message = failure.get("message", "batch apply failed")
    status_code = {
        "ACTION_NOT_FOUND": 404,
        "DESTINATION_COLLISION": 409,
        "SOURCE_OUTSIDE_ROOT": 422,
        "DESTINATION_OUTSIDE_ROOT": 422,
        "DELETE_SOURCE_MISSING": 404,
    }.get(code, 422)
    raise HTTPException(status_code=status_code, detail={"code": code, "message": message})


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
    batch_id = batch_for(proposal_id)
    if batch_id is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "BATCH_NOT_FOUND", "message": f"no batch recorded for proposal: {proposal_id}"},
        )
    if batch_id.startswith("noop_"):
        return {"ok": True, "proposal_id": proposal_id, "applied": True}
    result = apply_action_batch(batch_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "BATCH_NOT_FOUND", "message": f"unknown batch_id: {batch_id}"},
        )
    if result["failed"]:
        _raise_from_batch_failure(result)
    return {"ok": True, "proposal_id": proposal_id, "applied": True}


@router.post(
    "/proposals/{proposal_id}/undo",
    summary="Undo an applied organize proposal batch",
)
async def undo_organize_proposal(proposal_id: str):
    batch_id = batch_for(proposal_id)
    if batch_id is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "BATCH_NOT_FOUND", "message": f"no batch recorded for proposal: {proposal_id}"},
        )
    if batch_id.startswith("noop_"):
        return {"ok": True, "proposal_id": proposal_id, "undone": True}
    result = undo_action_batch(batch_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "BATCH_NOT_FOUND", "message": f"unknown batch_id: {batch_id}"},
        )
    return {"ok": True, "proposal_id": proposal_id, "undone": True}


@router.post(
    "/batches/{batch_id}/apply",
    summary="Apply an organize action batch",
)
async def apply_organize_batch(batch_id: str):
    result = apply_action_batch(batch_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "BATCH_NOT_FOUND", "message": f"unknown batch_id: {batch_id}"},
        )
    if result["failed"]:
        _raise_from_batch_failure(result)
    return {"ok": True, "batch_id": batch_id, "applied": True}


@router.post(
    "/batches/{batch_id}/undo",
    summary="Undo an organize action batch",
)
async def undo_organize_batch(batch_id: str):
    result = undo_action_batch(batch_id)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "BATCH_NOT_FOUND", "message": f"unknown batch_id: {batch_id}"},
        )
    return {"ok": True, "batch_id": batch_id, "undone": True}

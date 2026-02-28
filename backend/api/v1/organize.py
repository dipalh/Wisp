from pathlib import Path

from fastapi import APIRouter, HTTPException

from services.actions import Action, ActionStatus, ActionType
from services.actions import add as add_action
from services.organizer.models import DirectorySuggestions
from services.organizer.suggester import suggest_directories

router = APIRouter()


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

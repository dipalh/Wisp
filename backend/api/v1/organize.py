from fastapi import APIRouter, HTTPException

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
    """
    try:
        return await suggest_directories()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Organizer failed: {e}")

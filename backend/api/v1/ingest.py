from pathlib import Path

from fastapi import APIRouter, HTTPException

from services.embedding import store
from services.ingestor import ingest_directory

router = APIRouter()


@router.post(
    "/directory",
    summary="Scan and index a local directory",
)
async def ingest_local_directory(path: str, classify: bool = False):
    """
    Recursively scan *path* and ingest every file into the vector index.

    - Files over 100 MB use filename-based semantic inference (never read into RAM).
    - Files 8–100 MB that are Gemini-bound (PDFs, images) also use filename inference.
    - All other files are fully extracted by the dispatcher.

    If `classify=true`, each file is also classified by Gemini after ingestion and
    moved into *path*/<Category>/ (School, Work, Legal, Receipts, Media, Code,
    Personal) or *path*/Unsorted/ when confidence is low.  An APPLIED MOVE action
    is recorded for every file so classifications can be undone via the Action Engine.

    Returns the number of files indexed and total chunk count.
    """
    root = Path(path)
    if not root.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {path}")

    try:
        count = await ingest_directory(root, classify=classify)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Ingestion failed: {e}")

    return {"indexed": count, "chunks": store.collection_count()}

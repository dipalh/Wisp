"""
Semantic search API — Flow 2 entry point.

Routes
------
  POST /api/v1/search    Semantic search over the indexed vector store

Flow
----
  Client POSTs a query string.
  Server embeds the query (Gemini), queries LanceDB for top-k hits,
  applies Root Scope Guard filtering, and returns ranked results.

  Root scope filtering: if roots are registered, only results whose
  file_path falls under a registered root are returned.  If no roots
  are registered (open mode) all results pass through — consistent
  with how is_under_root() works.

Notes
-----
  pipeline.search() is synchronous (it calls embed_text() which is a
  blocking network call).  The route is defined as a plain `def` so
  FastAPI runs it in its thread-pool executor automatically, keeping
  the event loop free.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.embedding import pipeline
from services.file_state import normalize_error_code, normalize_error_message
from services.job_db import get_indexed_state_map
from services.roots import is_under_root

router = APIRouter()


class SearchRequest(BaseModel):
    query: str
    k:   int           = Field(default=10, ge=1, le=50, description="Max results to return")
    ext: Optional[str] = Field(default=None, description="Filter by extension, e.g. '.pdf'")


@router.post("", summary="Semantic search over indexed files")
def semantic_search(body: SearchRequest):
    """Embed *query* and return the top-k most semantically similar file chunks.

    Results are filtered to only include files under registered roots
    (or all files if no roots are set).

    Args:
        query: Natural-language search string.
        k:     Maximum number of results (1–50, default 10).
        ext:   Optional extension filter, e.g. ``".pdf"`` or ``".py"``.

    Returns:
        results   — ranked list of matching file chunks
        query     — echoed back for the client
        total     — number of results returned
    """
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    where = {"ext": body.ext} if body.ext else None
    hits  = pipeline.search(body.query, k=body.k, where=where)

    # Root scope guard — drop hits whose file is outside all registered roots
    hits = [h for h in hits if is_under_root(h.file_path or "")]
    state_map = get_indexed_state_map([h.file_id for h in hits])

    results = [
        {
            "file_id":   h.file_id,
            "file_path": h.file_path,
            "ext":       h.ext,
            "score":     h.score,
            "snippet":   h.text[:300],
            "depth":     h.depth,
            "file_state": state_map.get(h.file_id, {}).get("file_state", "INDEXED"),
            "error_code": normalize_error_code(
                state_map.get(h.file_id, {}).get("file_state", "INDEXED"),
                state_map.get(h.file_id, {}).get("error_code", ""),
            ),
            "error_message": normalize_error_message(
                state_map.get(h.file_id, {}).get("file_state", "INDEXED"),
                state_map.get(h.file_id, {}).get("error_message", ""),
            ),
        }
        for h in hits
    ]

    return {"results": results, "query": body.query, "total": len(results)}

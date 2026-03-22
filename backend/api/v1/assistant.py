"""
Assistant API — Flow 3 entry point.

Routes
------
  POST /api/v1/assistant    RAG query -> answer + action proposals

Flow
----
  1. Client POSTs a query string.
  2. Server calls pipeline.ask(query):
       - embeds query (Gemini)
       - retrieves top-k chunks from LanceDB
       - optionally deepens card/preview hits (more Gemini calls)
       - generates an answer via Gemini RAG
  3. Server calls proposer.propose_from_hits(hits):
       - scores each unique file in the hits with the Heuristics Engine
       - records PROPOSED actions for junk files
       - returns structured proposal dicts
  4. Returns {answer, proposals[], query, sources[], deepened_files[]}

Client responsibilities (after receiving the response)
-------------------------------------------------------
  - Show the answer in the chat panel
  - Render each proposal as an action card (label, junk_score, reasons)
  - On user "Apply": POST /api/v1/actions/{action_id}/apply
  - On user "Dismiss": POST /api/v1/actions/{action_id}/undo  (marks UNDONE)
  - On undo toast: POST /api/v1/actions/{action_id}/undo
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.embedding import pipeline
from services.file_state import normalize_error_code, normalize_error_message
from services.job_db import get_indexed_state_map
from services.proposer import propose_from_hits

router = APIRouter()


class AssistantRequest(BaseModel):
    query:       str
    k:           int           = Field(default=15, ge=1, le=50)
    auto_deepen: bool          = Field(default=True)
    ext:         Optional[str] = Field(default=None)


def _attach_proposal_citations(
    proposals: list[dict],
    *,
    default_citations: list[str],
) -> list[dict]:
    """Guarantee each proposal carries at least one evidence citation."""
    normalized: list[dict] = []
    for proposal in proposals:
        updated = dict(proposal)
        citations = [c for c in (updated.get("citations") or []) if c]
        if not citations:
            file_path = updated.get("file_path")
            if file_path:
                citations = [file_path]
            elif default_citations:
                citations = [default_citations[0]]
        updated["citations"] = citations
        normalized.append(updated)
    return normalized


@router.post("", summary="Ask the assistant — returns answer + action proposals")
async def ask_assistant(body: AssistantRequest):
    """Run a RAG query and return an answer with optional cleanup proposals.

    Args:
        query:       Natural-language question about the user's files.
        k:           Number of chunks to retrieve for context (default 15).
        auto_deepen: Whether to upgrade card/preview hits to full extraction
                     before answering (default True).
        ext:         Optional extension filter applied to retrieval.

    Returns:
        answer        — AI-generated response grounded in file contents
        proposals     — list of PROPOSED actions for junk files found in results
        query         — echoed back
        sources       — deduplicated list of file paths that contributed to answer
        deepened_files — files upgraded to full extraction during this call
    """
    if not body.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")

    where = {"ext": body.ext} if body.ext else None

    degraded = False
    warnings: list[str] = []
    confidence = 0.9
    try:
        result = await pipeline.ask(
            body.query,
            k=body.k,
            where=where,
            auto_deepen=body.auto_deepen,
        )
    except Exception as exc:
        degraded = True
        confidence = 0.35
        warnings.append(
            "ASSISTANT_DEGRADED: LLM unavailable, returned retrieval-grounded fallback."
        )
        hits = pipeline.search(body.query, k=body.k, where=where)
        result = type(
            "FallbackAskResult",
            (),
            {
                "answer": (
                    "I could not run full assistant generation right now, but I found relevant files "
                    "in your local index."
                ),
                "hits": hits,
                "query": body.query,
                "deepened_files": [],
            },
        )()

    # Generate proposals from the files that surfaced in the answer
    proposals = propose_from_hits(result.hits)
    state_map = get_indexed_state_map([hit.file_id for hit in result.hits])

    # Build a deduplicated sources list (file paths, no chunk noise)
    seen: set[str] = set()
    sources: list[str] = []
    source_details: list[dict[str, str]] = []
    for hit in result.hits:
        label = hit.file_path or hit.file_id
        if label and label not in seen:
            seen.add(label)
            sources.append(label)
            state = state_map.get(hit.file_id, {})
            source_details.append(
                {
                    "file_id": hit.file_id,
                    "file_path": hit.file_path,
                    "file_state": state.get("file_state", "INDEXED"),
                    "error_code": normalize_error_code(
                        state.get("file_state", "INDEXED"),
                        state.get("error_code", ""),
                    ),
                    "error_message": normalize_error_message(
                        state.get("file_state", "INDEXED"),
                        state.get("error_message", ""),
                    ),
                }
            )

    if not result.hits and not degraded:
        confidence = 0.2
        warnings.append(
            "NO_INDEX_RESULTS: No matching indexed files were found for this query."
        )

    proposals = _attach_proposal_citations(proposals, default_citations=sources)

    return {
        "answer":         result.answer,
        "proposals":      proposals,
        "query":          result.query,
        "sources":        sources,
        "source_details": source_details,
        "deepened_files": result.deepened_files,
        "confidence":     confidence,
        "warnings":       warnings,
        "degraded":       degraded,
    }

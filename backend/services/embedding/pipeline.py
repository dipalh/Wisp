"""
Embedding pipeline — the glue between extraction, chunking, and the vector store.

Public surface
--------------
  ingest(result, file_id)           — ContentResult → chunks → embeddings → LanceDB
  search(query, k, where)           — query string → LanceDB top-k hits
  ask(query, k, where)              — RAG: search + Gemini answer with citations
  delete_file(file_id)              — remove a file's chunks from LanceDB

These are the only functions the rest of the app (scan pipeline, search endpoint,
agent tool router) should call.  The chunker and store are implementation details.

Idempotency guarantee
---------------------
`ingest` always calls `delete_by_file_id` before upserting, so re-indexing a
file never produces duplicate chunks.  Callers must therefore pass a stable
`file_id` (e.g. sha256 of path|size|mtime) that does NOT change unless the
file actually changed.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from ai.embed import embed_batch, embed_text
from ai.generate import generate_text
from services.embedding.chunker import Chunk, chunk_text
from services.embedding import store
from services.embedding.store import SearchHit
from services.file_processor.models import ContentResult


# ── Result types ─────────────────────────────────────────────────────────────


@dataclass
class IngestResult:
    file_id: str
    file_path: str
    chunk_count: int
    skipped: bool = False          # True when text was empty (nothing to embed)
    errors: list[str] = field(default_factory=list)


@dataclass
class AskResult:
    """Structured result from the RAG ``ask()`` function."""
    answer: str                    # Gemini-generated answer grounded in the chunks
    hits: list[SearchHit]          # The raw retrieval results used as context
    query: str                     # The original query (echoed back for display)


# ── Core pipeline ─────────────────────────────────────────────────────────────


def ingest(
    result: ContentResult,
    file_id: str,
    *,
    chunk_size: int = 800,
    overlap: int = 100,
) -> IngestResult:
    """
    Ingest a single extracted file into the vector store.

    Steps
    -----
    1. Chunk ``result.content`` into ≤``chunk_size``-char segments.
    2. Batch-embed all chunks with Gemini gemini-embedding-001.
    3. Delete any existing chunks for ``file_id`` (idempotency).
    4. Upsert new chunks + embeddings into LanceDB.
    5. Return an IngestResult with counts and any non-fatal errors.

    Args:
        result:     ContentResult produced by the file-processor extractor.
        file_id:    Stable, unique ID for the source file (caller's responsibility).
        chunk_size: Max characters per chunk.
        overlap:    Characters carried over on a hard-split boundary.

    Returns:
        IngestResult
    """
    file_path = result.filename or result.file_name or ""
    ext = result.mime_type  # use ext field when available

    # ── 1. Chunk ──────────────────────────────────────────────────────────────
    chunks: list[Chunk] = chunk_text(
        result.content,
        file_id=file_id,
        chunk_size=chunk_size,
        overlap=overlap,
    )

    if not chunks:
        return IngestResult(
            file_id=file_id,
            file_path=file_path,
            chunk_count=0,
            skipped=True,
        )

    # ── 2. Embed ──────────────────────────────────────────────────────────────
    errors: list[str] = []
    try:
        embeddings = embed_batch([c.text for c in chunks])
    except Exception as exc:
        return IngestResult(
            file_id=file_id,
            file_path=file_path,
            chunk_count=0,
            errors=[f"Embedding API failed: {exc}"],
        )

    # ── 3. Delete old chunks (idempotency) ────────────────────────────────────
    try:
        store.delete_by_file_id(file_id)
    except Exception as exc:
        errors.append(f"Delete-before-upsert warning: {exc}")

    # ── 4. Upsert ─────────────────────────────────────────────────────────────
    try:
        store.upsert_chunks(
            chunks=chunks,
            embeddings=embeddings,
            file_path=file_path,
            ext=ext,
        )
    except Exception as exc:
        errors.append(f"Upsert failed: {exc}")
        return IngestResult(
            file_id=file_id,
            file_path=file_path,
            chunk_count=0,
            errors=errors,
        )

    return IngestResult(
        file_id=file_id,
        file_path=file_path,
        chunk_count=len(chunks),
        errors=errors,
    )


# ── Search ────────────────────────────────────────────────────────────────────


def search(
    query: str,
    k: int = 5,
    where: dict | None = None,
) -> list[SearchHit]:
    """
    Semantic search over indexed files.

    Args:
        query: Natural-language query string.
        k:     Maximum number of results to return.
        where: Optional LanceDB metadata filter (e.g. ``{"ext": ".pdf"}``).

    Returns:
        List of SearchHit ordered by descending similarity score.
    """
    query_embedding = embed_text(query)
    return store.query(query_embedding, k=k, where=where)


# ── RAG (Retrieve → Answer → Ground) ─────────────────────────────────────────

_RAG_SYSTEM = """\
You are Wisp, an intelligent file assistant.  The user is asking about files
on their computer.  Below are excerpts retrieved from those files.

Rules:
• Answer ONLY from the provided excerpts.  Do NOT hallucinate.
• If the excerpts don't contain enough info, say so honestly.
• Cite the source file name in your answer (e.g. "According to invoice.txt …").
• Keep answers concise but complete.
"""


def _build_rag_prompt(query: str, hits: list[SearchHit]) -> str:
    """Build the user-role prompt that includes retrieved context."""
    parts: list[str] = ["### Retrieved excerpts\n"]
    for i, h in enumerate(hits, 1):
        label = h.file_path or h.file_id
        parts.append(f"[{i}] Source: {label}\n{h.text}\n")
    parts.append(f"### Question\n{query}")
    return "\n".join(parts)


def ask(
    query: str,
    k: int = 5,
    where: dict | None = None,
) -> AskResult:
    """
    RAG pipeline: retrieve relevant chunks then ask Gemini for a grounded answer.

    This is the main entry-point the agent / search UI should call.

    Args:
        query: Natural-language question.
        k:     Number of chunks to retrieve.
        where: Optional metadata filter.

    Returns:
        AskResult with the AI answer, the raw hits, and the original query.
    """
    hits = search(query, k=k, where=where)
    if not hits:
        return AskResult(
            answer="I couldn't find any relevant information in the indexed files.",
            hits=[],
            query=query,
        )

    prompt = _build_rag_prompt(query, hits)
    # generate_text is async — run it synchronously here so callers
    # don't need to care about the async boundary.
    answer = asyncio.run(generate_text(prompt, system=_RAG_SYSTEM))
    return AskResult(answer=answer, hits=hits, query=query)


# ── Deletion ──────────────────────────────────────────────────────────────────


def delete_file(file_id: str) -> None:
    """Remove all chunks for a file from the vector store (e.g. on file deletion)."""
    store.delete_by_file_id(file_id)


# ── Store lifecycle (delegated, for test convenience) ─────────────────────────


def init_store(db_path: str | None = None) -> None:
    """Initialise (or re-point) the underlying vector store."""
    store.init(db_path=db_path)


def teardown_store() -> None:
    """Close the vector store connection."""
    store.teardown()

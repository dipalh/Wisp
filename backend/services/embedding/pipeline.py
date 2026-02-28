"""
Embedding pipeline — the glue between extraction, chunking, and the vector store.

Public surface
--------------
  ingest(result, file_id)           — ContentResult → chunks → embeddings → Chroma
  search(query, k, where)           — query string → Chroma top-k hits
  delete_file(file_id)              — remove a file's chunks from Chroma

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

from dataclasses import dataclass, field

from ai.embed import embed_batch, embed_text
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
    2. Batch-embed all chunks with Gemini text-embedding-004.
    3. Delete any existing chunks for ``file_id`` (idempotency).
    4. Upsert new chunks + embeddings into Chroma.
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
        where: Optional Chroma metadata filter (e.g. ``{"ext": ".pdf"}``).

    Returns:
        List of SearchHit ordered by descending similarity score.
    """
    query_embedding = embed_text(query)
    return store.query(query_embedding, k=k, where=where)


# ── Deletion ──────────────────────────────────────────────────────────────────


def delete_file(file_id: str) -> None:
    """Remove all chunks for a file from the vector store (e.g. on file deletion)."""
    store.delete_by_file_id(file_id)

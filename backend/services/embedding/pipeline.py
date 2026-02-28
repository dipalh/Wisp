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


MAX_CHUNKS_PER_FILE = 50  # prevent any single file from flooding the index


def _downsample_chunks(chunks: list[Chunk], max_chunks: int = MAX_CHUNKS_PER_FILE) -> list[Chunk]:
    """Keep first + last + evenly-spaced middle chunks to stay within budget."""
    if len(chunks) <= max_chunks:
        return chunks
    if max_chunks <= 2:
        return chunks[:max_chunks]

    # Always keep first and last
    sampled = [chunks[0]]
    inner_budget = max_chunks - 2
    step = (len(chunks) - 2) / (inner_budget + 1)
    for i in range(1, inner_budget + 1):
        idx = int(i * step)
        sampled.append(chunks[idx])
    sampled.append(chunks[-1])

    # Re-index so chunk_index is sequential
    for new_idx, chunk in enumerate(sampled):
        chunk.chunk_index = new_idx
        chunk.chunk_id = f"{chunk.file_id}:{new_idx}"
    return sampled


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

    # ── 1b. Downsample if a file produced too many chunks ─────────────────
    chunks = _downsample_chunks(chunks)

    # ── 1c. Prepend a file "index card" so inventory queries work ─────────
    # Include a content preview so semantic search can match files by theme,
    # not just by filename.  E.g. searching "resumes" will match a card that
    # says 'Content preview: Sarah Johnson, Senior Data Scientist …'
    _preview_raw = result.content or ""
    _preview = _preview_raw[:300].replace("\n", " ").strip()
    card_text = (
        f"[FILE INDEX] This is \"{file_path}\", a {ext} file "
        f"processed by {result.engine_used} ({len(chunks)} content chunks).\n"
        f"Content preview: {_preview}"
    )
    card = Chunk(
        chunk_id=f"{file_id}:card",
        file_id=file_id,
        chunk_index=-1,  # special: comes before real chunks
        text=card_text,
    )
    all_chunks = [card] + chunks

    # ── 2. Embed ──────────────────────────────────────────────────────────────
    errors: list[str] = []
    try:
        embeddings = embed_batch([c.text for c in all_chunks])
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
            chunks=all_chunks,
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
        chunk_count=len(all_chunks),
        errors=errors,
    )


# ── Search ────────────────────────────────────────────────────────────────────


def search(
    query: str,
    k: int = 5,
    where: dict | None = None,
    max_per_file: int = 3,
) -> list[SearchHit]:
    """
    Semantic search over indexed files, with diversity.

    Retrieves more candidates than needed, then caps results per file_id so
    no single file dominates the result set.

    Args:
        query:        Natural-language query string.
        k:            Maximum number of results to return.
        where:        Optional LanceDB metadata filter.
        max_per_file: Max hits from any single file (set high to disable).

    Returns:
        List of SearchHit ordered by descending similarity score.
    """
    # Fetch extra candidates to allow diversity filtering
    fetch_k = max(k * 4, 20)
    query_embedding = embed_text(query)
    raw_hits = store.query(query_embedding, k=fetch_k, where=where)

    # Diversify: cap hits per file
    file_counts: dict[str, int] = {}
    diverse: list[SearchHit] = []
    for hit in raw_hits:
        count = file_counts.get(hit.file_id, 0)
        if count < max_per_file:
            diverse.append(hit)
            file_counts[hit.file_id] = count + 1
            if len(diverse) >= k:
                break

    return diverse


# ── RAG (Retrieve → Answer → Ground) ─────────────────────────────────────────

_RAG_SYSTEM = """\
You are Wisp — a smart, friendly file-system memory.  You know the user's
files inside and out because their contents have been indexed.

When answering:
- Be concise and natural — talk like a helpful friend, not a corporate bot.
  No filler phrases like "Based on the information provided" or "I'd be happy to help".
- Synthesise across files when relevant.  Don't just parrot chunks back.
- Cite files naturally: "your resume mentions…", "that Q3 report shows…",
  "the screenshot from dashboard.png has…"
- For broad questions ("what's in here?"), give a quick birds-eye overview
  of what kinds of files exist and what they cover.
- If something's only indexed by metadata (name/type/size but no contents),
  mention it exists but note you can't see inside it.
- If the excerpts don't answer the question, say so plainly — but mention
  what IS available so they know what to ask about.
- Keep it tight.  No essays unless they ask for detail.
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
    k: int = 15,
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

"""
LanceDB vector-store wrapper for the Wisp embedding pipeline.

Responsibilities:
  - Manage persistent LanceDB connections (default path or caller-supplied).
  - Upsert chunks (with pre-computed embeddings).
  - Delete all chunks that belong to a file (for re-index idempotency).
  - Query top-k nearest neighbours and return hydrated SearchHit objects.

Table schema ("wisp_chunks")
----------------------------
  chunk_id     : str   — "<file_id>:<chunk_index>"
  file_id      : str
  chunk_index  : int32
  file_path    : str
  ext          : str
  text         : str   — the raw chunk text (used as citation)
  depth        : str   — "card" | "preview" | "deep"
  tags         : str   — JSON-encoded list[str], cross-platform tag source of truth
  vector       : list<float32>[EMBED_DIM]  — gemini-embedding-001 vector
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import lancedb
import pyarrow as pa

from services.embedding.chunker import Chunk

# ── Config ───────────────────────────────────────────────────────────────────

_DEFAULT_PERSIST_DIR = str(Path.home() / ".wisp" / "lancedb")
TABLE_NAME = "wisp_chunks"
EMBED_DIM = 3072  # gemini-embedding-001 output dimension


def _default_persist_dir() -> str:
    return os.environ.get("WISP_LANCEDB_PATH", _DEFAULT_PERSIST_DIR)


# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA = pa.schema([
    pa.field("chunk_id",    pa.string()),
    pa.field("file_id",     pa.string()),
    pa.field("chunk_index", pa.int32()),
    pa.field("file_path",   pa.string()),
    pa.field("ext",         pa.string()),
    pa.field("text",        pa.string()),
    pa.field("depth",       pa.string()),
    pa.field("tags",        pa.string()),  # JSON-encoded list[str]
    pa.field("vector",      pa.list_(pa.float32(), EMBED_DIM)),
])

# Columns whose absence triggers a schema migration (drop + recreate).
_REQUIRED_COLS = {"depth", "tags"}


# ── Connection management ─────────────────────────────────────────────────────
#
# The default singleton is used by production code.  Tests (and anyone who needs
# isolation) call  init(db_path="/tmp/...")  to point at a fresh directory,
# then  teardown()  to close and reset.

_db: lancedb.DBConnection | None = None
_table: lancedb.table.Table | None = None
_db_path: str | None = None


def init(db_path: str | None = None) -> None:
    """Initialise (or re-initialise) the LanceDB connection.

    Args:
        db_path: Explicit directory.  If *None*, uses the WISP_LANCEDB_PATH
                 env-var or ``~/.wisp/lancedb``.
    """
    global _db, _table, _db_path
    _db_path = db_path or _default_persist_dir()
    Path(_db_path).mkdir(parents=True, exist_ok=True)
    _db = lancedb.connect(_db_path)
    _table = None  # will be lazily opened by _get_table()


def teardown() -> None:
    """Close the connection and reset module state.  Safe to call multiple times."""
    global _db, _table, _db_path
    _db = None
    _table = None
    _db_path = None


def _get_table() -> lancedb.table.Table:
    global _db, _table
    if _db is None:
        init()  # first call — use defaults
    if _table is None:
        existing = _db.table_names()
        if TABLE_NAME in existing:
            tbl = _db.open_table(TABLE_NAME)
            # Auto-migrate: drop table if schema is outdated
            col_names = [f.name for f in tbl.schema]
            if not _REQUIRED_COLS.issubset(col_names):
                _db.drop_table(TABLE_NAME)
                _table = _db.create_table(TABLE_NAME, schema=_SCHEMA)
            else:
                _table = tbl
        else:
            _table = _db.create_table(TABLE_NAME, schema=_SCHEMA)
    return _table


# ── Result type ──────────────────────────────────────────────────────────────


@dataclass
class SearchHit:
    chunk_id: str
    file_id: str
    chunk_index: int
    file_path: str
    ext: str
    text: str          # chunk text returned as context / citation
    score: float       # cosine similarity [0, 1]; higher = more similar
    depth: str = "deep"  # "card" | "preview" | "deep"
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ── Public API ───────────────────────────────────────────────────────────────


def upsert_chunks(
    chunks: list[Chunk],
    embeddings: list[list[float]],
    file_path: str = "",
    ext: str = "",
    depth: str = "deep",
    tags: list[str] | None = None,
) -> int:
    """
    Upsert pre-embedded chunks into LanceDB.

    Args:
        chunks:     Chunk objects produced by chunker.chunk_text().
        embeddings: Parallel list of float vectors (same order as chunks).
        file_path:  Original file path — stored for hydration.
        ext:        File extension (e.g. ".pdf") — stored for filtering.

    Returns:
        Number of chunks upserted.
    """
    if not chunks:
        return 0
    if len(chunks) != len(embeddings):
        raise ValueError(
            f"chunks ({len(chunks)}) and embeddings ({len(embeddings)}) must have equal length"
        )

    table = _get_table()
    tags_json = json.dumps(tags or [])
    rows = [
        {
            "chunk_id":    c.chunk_id,
            "file_id":     c.file_id,
            "chunk_index": c.chunk_index,
            "file_path":   file_path,
            "ext":         ext,
            "text":        c.text,
            "depth":       depth,
            "tags":        tags_json,
            "vector":      [float(v) for v in emb],
        }
        for c, emb in zip(chunks, embeddings)
    ]
    # LanceDB upsert: merge on chunk_id
    table.merge_insert("chunk_id").when_matched_update_all().when_not_matched_insert_all().execute(rows)
    return len(chunks)


def delete_by_file_id(file_id: str) -> None:
    """Remove all chunks belonging to `file_id` (call before re-indexing)."""
    table = _get_table()
    try:
        table.delete(f"file_id = '{file_id}'")
    except Exception:
        pass  # table may be empty; that's fine


def query(
    query_embedding: list[float],
    k: int = 5,
    where: dict[str, Any] | None = None,
) -> list[SearchHit]:
    """
    Find the top-k most similar chunks.

    Args:
        query_embedding: Float vector for the query (same model/dim as stored).
        k:               Number of results to return.
        where:           Optional sql-style filter string, e.g. "ext = '.pdf'",
                         OR a dict like {"ext": ".pdf"} (will be converted).

    Returns:
        List of SearchHit ordered by descending similarity score.
    """
    table = _get_table()
    n = min(k, collection_count() or k)

    search = table.search(query_embedding, vector_column_name="vector")
    search = search.limit(n)
    search = search.metric("cosine")

    # Convert dict filter to SQL string
    if isinstance(where, dict):
        clauses = [f"{col} = '{val}'" for col, val in where.items()]
        where = " AND ".join(clauses) if clauses else None
    if where:
        search = search.where(where)

    df = search.to_pandas()

    hits: list[SearchHit] = []
    for _, row in df.iterrows():
        # LanceDB cosine returns distance in [0,1] where 0 = identical
        distance = float(row.get("_distance", 0.0))
        similarity = round(1.0 - distance, 4)
        hits.append(
            SearchHit(
                chunk_id=str(row["chunk_id"]),
                file_id=str(row["file_id"]),
                chunk_index=int(row["chunk_index"]),
                file_path=str(row["file_path"]),
                ext=str(row["ext"]),
                text=str(row["text"]),
                score=similarity,
                depth=str(row.get("depth", "deep")),
                tags=json.loads(row["tags"]) if row.get("tags") else [],
            )
        )

    return hits


def collection_count() -> int:
    """Return total number of chunks currently stored."""
    try:
        return _get_table().count_rows()
    except Exception:
        return 0


def reset_collection() -> None:
    """
    Drop and recreate the table.
    Use only in tests or when doing a full re-index from scratch.
    """
    global _table
    if _db is not None:
        try:
            _db.drop_table(TABLE_NAME)
        except Exception:
            pass
    _table = None
    _get_table()  # recreate empty table


def current_db_path() -> str | None:
    """Return the path the store is currently pointed at (for diagnostics)."""
    return _db_path


def list_files() -> list[dict]:
    """Return one record per indexed file (the index-card rows, chunk_index == -1)."""
    if collection_count() == 0:
        return []
    df = _get_table().to_pandas()
    cards = df[df["chunk_index"] == -1]
    records = cards[["file_id", "file_path", "ext", "text", "tags"]].to_dict("records")
    # Deserialise JSON tags
    for r in records:
        try:
            r["tags"] = json.loads(r.get("tags", "[]"))
        except Exception:
            r["tags"] = []
    return records


# ── Tag CRUD (index-backed, cross-platform) ─────────────────────────────────


def get_file_tags(file_id: str) -> list[str]:
    """Return the tags stored in the index for ``file_id``."""
    if collection_count() == 0:
        return []
    df = _get_table().to_pandas()
    card = df[(df["file_id"] == file_id) & (df["chunk_index"] == -1)]
    if card.empty:
        return []
    try:
        return json.loads(card.iloc[0]["tags"])
    except Exception:
        return []


def update_file_tags(file_id: str, tags: list[str]) -> bool:
    """Overwrite the tags for every chunk belonging to ``file_id``.

    This is the cross-platform source of truth.  For macOS Finder
    visibility, pair with ``tagger.add_tag()`` / ``tagger.remove_tag()``.
    """
    table = _get_table()
    tags_json = json.dumps(tags)
    try:
        # LanceDB doesn't support UPDATE in-place easily — read, mutate, merge.
        df = table.to_pandas()
        mask = df["file_id"] == file_id
        if not mask.any():
            return False
        df.loc[mask, "tags"] = tags_json
        rows = df[mask].to_dict("records")
        # Remove vector column conversion issues
        for r in rows:
            r["vector"] = [float(v) for v in r["vector"]]
        table.merge_insert("chunk_id").when_matched_update_all().when_not_matched_insert_all().execute(rows)
        return True
    except Exception:
        return False

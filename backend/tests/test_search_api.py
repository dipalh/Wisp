"""
Tests for POST /api/v1/search — semantic search endpoint.

Uses a minimal FastAPI app with only the search router mounted.
pipeline.search() is mocked to avoid needing Gemini API keys or
a populated LanceDB store.

Covers:
  - Empty query rejected with 400
  - Successful search returns correct response shape
  - Each result has required fields: file_id, file_path, ext, score, snippet, depth
  - Snippet is truncated to 300 chars
  - Empty results return total=0
  - query is echoed back in response
  - ext filter is passed through to pipeline
  - FastAPI startup initialises LanceDB store
  - FastAPI shutdown tears down LanceDB store
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    """TestClient against a minimal app with only the search router."""
    from api.v1.search import router as search_router
    test_app = FastAPI()
    test_app.include_router(search_router, prefix="/api/v1/search")
    return TestClient(test_app)


@dataclass
class _FakeSearchHit:
    chunk_id: str
    file_id: str
    chunk_index: int
    file_path: str
    ext: str
    text: str
    score: float
    depth: str = "deep"
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════
#  Validation
# ═══════════════════════════════════════════════════════════════════════


def test_empty_query_rejected(client):
    """POST with empty query must return 400."""
    resp = client.post("/api/v1/search", json={"query": ""})
    assert resp.status_code == 400
    assert "empty" in resp.json()["detail"].lower()


def test_whitespace_only_query_rejected(client):
    """POST with whitespace-only query must return 400."""
    resp = client.post("/api/v1/search", json={"query": "   "})
    assert resp.status_code == 400


def test_missing_query_rejected(client):
    """POST with no query field must return 422 (validation error)."""
    resp = client.post("/api/v1/search", json={})
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
#  Successful search — response shape
# ═══════════════════════════════════════════════════════════════════════


def test_search_returns_correct_shape(client):
    """Successful search returns {results, query, total} with correct field shapes."""
    fake_hits = [
        _FakeSearchHit(
            chunk_id="abc:0",
            file_id="abc",
            chunk_index=0,
            file_path="/Users/test/resume.pdf",
            ext=".pdf",
            text="Experienced software engineer with 5 years in Python and TypeScript",
            score=0.92,
            depth="deep",
        ),
        _FakeSearchHit(
            chunk_id="def:0",
            file_id="def",
            chunk_index=0,
            file_path="/Users/test/cover_letter.docx",
            ext=".docx",
            text="I am writing to express my interest in the position",
            score=0.87,
            depth="preview",
        ),
    ]

    with patch("api.v1.search.pipeline") as mock_pipeline, \
         patch("api.v1.search.is_under_root", return_value=True):
        mock_pipeline.search.return_value = fake_hits
        resp = client.post("/api/v1/search", json={"query": "find my resumes"})

    assert resp.status_code == 200
    data = resp.json()

    # Top-level shape
    assert "results" in data
    assert "query" in data
    assert "total" in data
    assert data["query"] == "find my resumes"
    assert data["total"] == 2
    assert len(data["results"]) == 2

    # Each result has required fields
    for result in data["results"]:
        assert "file_id" in result
        assert "file_path" in result
        assert "ext" in result
        assert "score" in result
        assert "snippet" in result
        assert "depth" in result
        assert isinstance(result["score"], float)
        assert isinstance(result["snippet"], str)

    # First result values
    r0 = data["results"][0]
    assert r0["file_id"] == "abc"
    assert r0["file_path"] == "/Users/test/resume.pdf"
    assert r0["ext"] == ".pdf"
    assert r0["score"] == 0.92
    assert r0["depth"] == "deep"
    assert "Experienced software engineer" in r0["snippet"]


def test_search_empty_results(client):
    """Search with no matches returns empty list and total=0."""
    with patch("api.v1.search.pipeline") as mock_pipeline, \
         patch("api.v1.search.is_under_root", return_value=True):
        mock_pipeline.search.return_value = []
        resp = client.post("/api/v1/search", json={"query": "unicorn documents"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["results"] == []
    assert data["total"] == 0
    assert data["query"] == "unicorn documents"


def test_search_snippet_truncated_to_300(client):
    """Snippet must be at most 300 characters, even if chunk text is longer."""
    long_text = "A" * 500
    fake_hit = _FakeSearchHit(
        chunk_id="x:0", file_id="x", chunk_index=0,
        file_path="/test.txt", ext=".txt",
        text=long_text, score=0.5, depth="deep",
    )

    with patch("api.v1.search.pipeline") as mock_pipeline, \
         patch("api.v1.search.is_under_root", return_value=True):
        mock_pipeline.search.return_value = [fake_hit]
        resp = client.post("/api/v1/search", json={"query": "test"})

    snippet = resp.json()["results"][0]["snippet"]
    assert len(snippet) == 300


def test_search_query_echoed_back(client):
    """The response must echo the query string back."""
    with patch("api.v1.search.pipeline") as mock_pipeline, \
         patch("api.v1.search.is_under_root", return_value=True):
        mock_pipeline.search.return_value = []
        resp = client.post("/api/v1/search", json={"query": "my tax returns"})

    assert resp.json()["query"] == "my tax returns"


def test_search_ext_filter_passed_to_pipeline(client):
    """When ext is provided, it should be passed to pipeline.search as where filter."""
    with patch("api.v1.search.pipeline") as mock_pipeline, \
         patch("api.v1.search.is_under_root", return_value=True):
        mock_pipeline.search.return_value = []
        client.post("/api/v1/search", json={"query": "report", "ext": ".pdf"})

    mock_pipeline.search.assert_called_once()
    call_kwargs = mock_pipeline.search.call_args
    assert call_kwargs[1].get("where") == {"ext": ".pdf"} or \
           (len(call_kwargs[0]) >= 3 and call_kwargs[0][2] == {"ext": ".pdf"})


def test_search_default_k_is_10(client):
    """Default k should be 10 when not specified."""
    with patch("api.v1.search.pipeline") as mock_pipeline, \
         patch("api.v1.search.is_under_root", return_value=True):
        mock_pipeline.search.return_value = []
        client.post("/api/v1/search", json={"query": "anything"})

    call_args = mock_pipeline.search.call_args
    assert call_args.kwargs.get("k") == 10


def test_search_custom_k(client):
    """Custom k value should be passed through."""
    with patch("api.v1.search.pipeline") as mock_pipeline, \
         patch("api.v1.search.is_under_root", return_value=True):
        mock_pipeline.search.return_value = []
        client.post("/api/v1/search", json={"query": "anything", "k": 5})

    call_args = mock_pipeline.search.call_args
    assert call_args.kwargs.get("k") == 5


def test_search_root_scope_filters_out_of_scope_hits(client):
    """Hits outside registered roots should be filtered out."""
    fake_hits = [
        _FakeSearchHit(
            chunk_id="in:0", file_id="in", chunk_index=0,
            file_path="/Users/test/Documents/resume.pdf",
            ext=".pdf", text="in scope", score=0.9, depth="deep",
        ),
        _FakeSearchHit(
            chunk_id="out:0", file_id="out", chunk_index=0,
            file_path="/etc/shadow",
            ext="", text="out of scope", score=0.8, depth="card",
        ),
    ]

    def _mock_under_root(path):
        return path.startswith("/Users/test")

    with patch("api.v1.search.pipeline") as mock_pipeline, \
         patch("api.v1.search.is_under_root", side_effect=_mock_under_root):
        mock_pipeline.search.return_value = fake_hits
        resp = client.post("/api/v1/search", json={"query": "resume"})

    data = resp.json()
    assert data["total"] == 1
    assert data["results"][0]["file_id"] == "in"


def test_search_results_include_index_state_fields(client):
    """Search results should surface reconciliation state + error fields."""
    fake_hits = [
        _FakeSearchHit(
            chunk_id="stale:0",
            file_id="stale",
            chunk_index=0,
            file_path="/Users/test/Documents/old.txt",
            ext=".txt",
            text="old note",
            score=0.8,
            depth="deep",
        ),
    ]

    with patch("api.v1.search.pipeline") as mock_pipeline, \
         patch("api.v1.search.is_under_root", return_value=True), \
         patch(
             "api.v1.search.get_indexed_state_map",
             return_value={
                 "stale": {
                     "file_state": "MISSING_EXTERNALLY",
                     "error_code": "MISSING_EXTERNALLY",
                     "error_message": "file no longer exists",
                 }
             },
             create=True,
         ):
        mock_pipeline.search.return_value = fake_hits
        resp = client.post("/api/v1/search", json={"query": "old note"})

    assert resp.status_code == 200
    result = resp.json()["results"][0]
    assert result["file_state"] == "MISSING_EXTERNALLY"
    assert result["error_code"] == "MISSING_EXTERNALLY"
    assert "no longer exists" in result["error_message"]


# ═══════════════════════════════════════════════════════════════════════
#  Store lifecycle — startup & shutdown
# ═══════════════════════════════════════════════════════════════════════


def test_app_startup_initialises_store(tmp_path):
    """The lifespan hook must call store.init() on startup."""
    import sys
    from unittest.mock import AsyncMock

    # Stub missing optional dependencies so main.py can be imported
    _STUB_MODS = ("elevenlabs", "elevenlabs.client")
    stubs = {}
    for mod in _STUB_MODS:
        if mod not in sys.modules:
            stubs[mod] = sys.modules[mod] = MagicMock()

    try:
        import importlib
        import main as main_mod
        importlib.reload(main_mod)

        with patch.object(main_mod, "store") as mock_store:
            with TestClient(main_mod.app):
                mock_store.init.assert_called_once()
    finally:
        for mod in stubs:
            sys.modules.pop(mod, None)


def test_app_shutdown_tears_down_store(tmp_path):
    """The lifespan hook must call store.teardown() on shutdown."""
    import sys

    _STUB_MODS = ("elevenlabs", "elevenlabs.client")
    stubs = {}
    for mod in _STUB_MODS:
        if mod not in sys.modules:
            stubs[mod] = sys.modules[mod] = MagicMock()

    try:
        import importlib
        import main as main_mod
        importlib.reload(main_mod)

        with patch.object(main_mod, "store") as mock_store:
            tc = TestClient(main_mod.app)
            tc.__enter__()
            tc.__exit__(None, None, None)
            mock_store.teardown.assert_called_once()
    finally:
        for mod in stubs:
            sys.modules.pop(mod, None)


# ═══════════════════════════════════════════════════════════════════════
#  k parameter boundary validation
# ═══════════════════════════════════════════════════════════════════════


def test_k_zero_rejected(client):
    """k=0 must be rejected (min is 1)."""
    resp = client.post("/api/v1/search", json={"query": "test", "k": 0})
    assert resp.status_code == 422


def test_k_above_50_rejected(client):
    """k=51 must be rejected (max is 50)."""
    resp = client.post("/api/v1/search", json={"query": "test", "k": 51})
    assert resp.status_code == 422


def test_k_max_accepted(client):
    """k=50 (the maximum) should be accepted."""
    with patch("api.v1.search.pipeline") as mock_pipeline, \
         patch("api.v1.search.is_under_root", return_value=True):
        mock_pipeline.search.return_value = []
        resp = client.post("/api/v1/search", json={"query": "test", "k": 50})

    assert resp.status_code == 200


def test_k_one_accepted(client):
    """k=1 (the minimum) should be accepted."""
    with patch("api.v1.search.pipeline") as mock_pipeline, \
         patch("api.v1.search.is_under_root", return_value=True):
        mock_pipeline.search.return_value = []
        resp = client.post("/api/v1/search", json={"query": "test", "k": 1})

    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════
#  Real LanceDB store integration — search after index
# ═══════════════════════════════════════════════════════════════════════


_EMBED_DIM = 3072


def _dummy_vector() -> list[float]:
    return [0.1] * _EMBED_DIM


@pytest.fixture()
def real_store(tmp_path):
    """Provide a real (temporary) LanceDB store for integration tests."""
    from services.embedding import store as real_store_mod
    real_store_mod.init(db_path=str(tmp_path / "test_lance"))
    yield real_store_mod
    real_store_mod.teardown()


def test_search_empty_real_store_returns_zero_results(real_store):
    """pipeline.search() against an empty LanceDB table returns [] without crashing."""
    from services.embedding import pipeline

    with patch.object(pipeline, "embed_text", return_value=_dummy_vector()):
        results = pipeline.search("anything at all", k=5)

    assert results == []


def test_search_real_store_finds_indexed_content(real_store):
    """After ingesting content into real LanceDB, pipeline.search() returns hits."""
    from services.embedding import pipeline
    from services.embedding.chunker import Chunk

    chunks = [
        Chunk(chunk_id="resume:card", file_id="resume", chunk_index=-1,
              text="[FILE INDEX] resume.pdf — experienced software engineer"),
        Chunk(chunk_id="resume:0", file_id="resume", chunk_index=0,
              text="Experienced software engineer with 5 years of Python, TypeScript, and React."),
        Chunk(chunk_id="resume:1", file_id="resume", chunk_index=1,
              text="Led migration of monolith to microservices, reducing deploy time by 70%."),
    ]
    embeddings = [_dummy_vector() for _ in chunks]
    real_store.upsert_chunks(
        chunks=chunks, embeddings=embeddings,
        file_path="/Users/test/resume.pdf", ext=".pdf", depth="deep",
    )

    with patch.object(pipeline, "embed_text", return_value=_dummy_vector()):
        results = pipeline.search("software engineer resume", k=5)

    assert len(results) > 0
    file_ids = {h.file_id for h in results}
    assert "resume" in file_ids
    assert all(isinstance(h.score, float) for h in results)
    assert all(h.file_path == "/Users/test/resume.pdf" for h in results)


def test_search_diversity_caps_per_file(real_store):
    """pipeline.search() max_per_file limits how many chunks return per file_id."""
    from services.embedding import pipeline
    from services.embedding.chunker import Chunk

    chunks = []
    embeddings = []
    for i in range(10):
        chunks.append(Chunk(
            chunk_id=f"bigfile:{i}", file_id="bigfile", chunk_index=i,
            text=f"Chunk {i} of a very large document with lots of content.",
        ))
        embeddings.append(_dummy_vector())

    real_store.upsert_chunks(
        chunks=chunks, embeddings=embeddings,
        file_path="/Users/test/big.txt", ext=".txt", depth="deep",
    )

    with patch.object(pipeline, "embed_text", return_value=_dummy_vector()):
        results = pipeline.search("large document", k=10, max_per_file=2)

    bigfile_hits = [h for h in results if h.file_id == "bigfile"]
    assert len(bigfile_hits) <= 2


def test_search_multiple_files_returns_diverse_results(real_store):
    """Search across multiple indexed files returns results from each."""
    from services.embedding import pipeline
    from services.embedding.chunker import Chunk

    for name, fid, text in [
        ("resume.pdf", "f-resume", "Software engineer with Python experience"),
        ("budget.csv", "f-budget", "Q3 2025 revenue breakdown by region"),
        ("notes.md", "f-notes", "Meeting notes discussing product roadmap"),
    ]:
        chunks = [
            Chunk(chunk_id=f"{fid}:card", file_id=fid, chunk_index=-1,
                  text=f"[FILE INDEX] {name}"),
            Chunk(chunk_id=f"{fid}:0", file_id=fid, chunk_index=0, text=text),
        ]
        real_store.upsert_chunks(
            chunks=chunks, embeddings=[_dummy_vector(), _dummy_vector()],
            file_path=f"/Users/test/{name}", ext=f".{name.split('.')[-1]}", depth="deep",
        )

    with patch.object(pipeline, "embed_text", return_value=_dummy_vector()):
        results = pipeline.search("find my files", k=10)

    file_ids = {h.file_id for h in results}
    assert len(file_ids) >= 2, f"Expected results from multiple files, got: {file_ids}"


def test_search_endpoint_with_real_store(real_store):
    """POST /api/v1/search against a real populated store returns correct HTTP response."""
    from services.embedding import pipeline
    from services.embedding.chunker import Chunk

    chunks = [
        Chunk(chunk_id="tax:card", file_id="tax", chunk_index=-1,
              text="[FILE INDEX] tax_return_2025.pdf"),
        Chunk(chunk_id="tax:0", file_id="tax", chunk_index=0,
              text="Federal tax return for fiscal year 2025, total income $120,000."),
    ]
    real_store.upsert_chunks(
        chunks=chunks, embeddings=[_dummy_vector(), _dummy_vector()],
        file_path="/Users/test/tax_return_2025.pdf", ext=".pdf", depth="deep",
    )

    from api.v1.search import router as search_router
    test_app = FastAPI()
    test_app.include_router(search_router, prefix="/api/v1/search")

    with patch.object(pipeline, "embed_text", return_value=_dummy_vector()), \
         patch("api.v1.search.is_under_root", return_value=True):
        with TestClient(test_app) as tc:
            resp = tc.post("/api/v1/search", json={"query": "tax return", "k": 5})

    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] > 0
    assert data["query"] == "tax return"
    file_paths = [r["file_path"] for r in data["results"]]
    assert "/Users/test/tax_return_2025.pdf" in file_paths
    for r in data["results"]:
        assert "file_id" in r
        assert "snippet" in r
        assert "score" in r
        assert "depth" in r
        assert len(r["snippet"]) <= 300

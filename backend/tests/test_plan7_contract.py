from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@dataclass
class _FakeHit:
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


def _assistant_client() -> TestClient:
    from api.v1.assistant import router as assistant_router

    app = FastAPI()
    app.include_router(assistant_router, prefix="/api/v1/assistant")
    return TestClient(app)


def _search_client() -> TestClient:
    from api.v1.search import router as search_router

    app = FastAPI()
    app.include_router(search_router, prefix="/api/v1/search")
    return TestClient(app)


def test_assistant_ask_failure_returns_grounded_degraded_payload():
    client = _assistant_client()
    hits = [
        _FakeHit(
            chunk_id="doc:0",
            file_id="doc",
            chunk_index=0,
            file_path="/Users/test/Documents/notes.txt",
            ext=".txt",
            text="important local note",
            score=0.91,
            depth="deep",
        )
    ]

    with patch("api.v1.assistant.pipeline.ask", new=AsyncMock(side_effect=RuntimeError("llm unavailable"))), \
         patch("api.v1.assistant.pipeline.search", return_value=hits), \
         patch("api.v1.assistant.propose_from_hits", return_value=[]), \
         patch("api.v1.assistant.get_indexed_state_map", return_value={"doc": {"file_state": "INDEXED"}}):
        resp = client.post("/api/v1/assistant", json={"query": "what is in my notes?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["query"] == "what is in my notes?"
    assert body["sources"] == ["/Users/test/Documents/notes.txt"]
    assert body["source_details"][0]["file_id"] == "doc"
    assert body["warnings"] == ["ASSISTANT_DEGRADED: LLM unavailable, returned retrieval-grounded fallback."]
    assert body["confidence"] == 0.35
    assert body["degraded"] is True


def test_assistant_proposals_are_always_tied_to_hit_citations():
    client = _assistant_client()
    hits = [
        _FakeHit(
            chunk_id="doc:0",
            file_id="doc",
            chunk_index=0,
            file_path="/Users/test/Documents/report.txt",
            ext=".txt",
            text="report details",
            score=0.92,
            depth="deep",
        )
    ]
    fake_result = type(
        "FakeAskResult",
        (),
        {"answer": "report summary", "hits": hits, "query": "summarize report", "deepened_files": []},
    )()
    raw_proposals = [
        {
            "action_id": "a1",
            "file_path": "/Users/test/Documents/report.txt",
            "label": "Quarantine report.txt",
            "junk_score": 0.87,
            "reasons": ["old temp artifact"],
            "action_type": "MOVE",
            "destination": "/Users/test/Documents/.wisp_quarantine/report.txt",
            "citations": [],
        }
    ]

    with patch("api.v1.assistant.pipeline.ask", new=AsyncMock(return_value=fake_result)), \
         patch("api.v1.assistant.propose_from_hits", return_value=raw_proposals), \
         patch("api.v1.assistant.get_indexed_state_map", return_value={"doc": {"file_state": "INDEXED"}}):
        resp = client.post("/api/v1/assistant", json={"query": "summarize report"})

    assert resp.status_code == 200
    body = resp.json()
    assert len(body["proposals"]) == 1
    proposal = body["proposals"][0]
    assert proposal["citations"] == ["/Users/test/Documents/report.txt"]


@pytest.mark.anyio
async def test_ask_auto_deepen_dedupes_hits_and_respects_unique_budget(tmp_path):
    from services.embedding import pipeline
    from services.embedding.pipeline import IngestResult
    from services.embedding.store import SearchHit

    a = tmp_path / "a.pdf"
    b = tmp_path / "b.pdf"
    c = tmp_path / "c.pdf"
    d = tmp_path / "d.pdf"
    for p in (a, b, c, d):
        p.write_text("doc")

    hits = [
        SearchHit("a:0", "a", 0, str(a), ".pdf", "a text", 0.92, depth="card"),
        SearchHit("a:1", "a", 1, str(a), ".pdf", "a text 2", 0.91, depth="preview"),
        SearchHit("b:0", "b", 0, str(b), ".pdf", "b text", 0.90, depth="preview"),
        SearchHit("c:0", "c", 0, str(c), ".pdf", "c text", 0.89, depth="card"),
        SearchHit("d:0", "d", 0, str(d), ".pdf", "d text", 0.88, depth="preview"),
    ]

    async def _fake_deepen(file_path: Path | str, file_id: str | None = None):
        return IngestResult(
            file_id=file_id or "x",
            file_path=str(file_path),
            chunk_count=1,
            depth="deep",
            engine="gemini",
        )

    with patch("services.embedding.pipeline._search_async", new=AsyncMock(side_effect=[hits, hits])), \
         patch("services.embedding.pipeline.deepen_file", new=AsyncMock(side_effect=_fake_deepen)) as deepen_mock, \
         patch("services.embedding.pipeline.generate_text", new=AsyncMock(return_value="ok answer")):
        result = await pipeline.ask("summarize files", k=5, auto_deepen=True)

    assert result.answer == "ok answer"
    assert len(result.deepened_files) == 3
    assert len(set(result.deepened_files)) == 3
    assert str(a) in result.deepened_files
    assert str(b) in result.deepened_files
    assert str(c) in result.deepened_files
    assert deepen_mock.await_count == 3


def test_search_reranks_indexed_deep_results_ahead_of_stale_even_with_lower_score():
    client = _search_client()
    stale_high_score = _FakeHit(
        chunk_id="stale:0",
        file_id="stale",
        chunk_index=0,
        file_path="/Users/test/Documents/stale.txt",
        ext=".txt",
        text="stale result",
        score=0.99,
        depth="deep",
    )
    indexed_lower_score = _FakeHit(
        chunk_id="indexed:0",
        file_id="indexed",
        chunk_index=0,
        file_path="/Users/test/Documents/indexed.txt",
        ext=".txt",
        text="indexed result",
        score=0.75,
        depth="deep",
    )
    with patch("api.v1.search.pipeline.search", return_value=[stale_high_score, indexed_lower_score]), \
         patch("api.v1.search.is_under_root", return_value=True), \
         patch(
             "api.v1.search.get_indexed_state_map",
             return_value={
                 "stale": {"file_state": "STALE", "error_code": "STALE", "error_message": "stale"},
                 "indexed": {"file_state": "INDEXED", "error_code": "", "error_message": ""},
             },
         ):
        resp = client.post("/api/v1/search", json={"query": "find notes"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["results"][0]["file_id"] == "indexed"
    assert body["results"][1]["file_id"] == "stale"


def test_assistant_empty_hits_returns_explicit_actionable_warning():
    client = _assistant_client()
    fake_result = type(
        "FakeAskResult",
        (),
        {
            "answer": "I couldn't find any relevant information in the indexed files.",
            "hits": [],
            "query": "anything here?",
            "deepened_files": [],
        },
    )()
    with patch("api.v1.assistant.pipeline.ask", new=AsyncMock(return_value=fake_result)), \
         patch("api.v1.assistant.propose_from_hits", return_value=[]), \
         patch("api.v1.assistant.get_indexed_state_map", return_value={}):
        resp = client.post("/api/v1/assistant", json={"query": "anything here?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["sources"] == []
    assert body["proposals"] == []
    assert body["confidence"] == 0.2
    assert body["warnings"] == ["NO_INDEX_RESULTS: No matching indexed files were found for this query."]

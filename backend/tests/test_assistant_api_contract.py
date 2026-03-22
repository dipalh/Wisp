from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, patch

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


@dataclass
class _FakeAskResult:
    answer: str
    hits: list[_FakeHit]
    query: str
    deepened_files: list[str] = field(default_factory=list)


def _client() -> TestClient:
    from api.v1.assistant import router as assistant_router

    test_app = FastAPI()
    test_app.include_router(assistant_router, prefix="/api/v1/assistant")
    return TestClient(test_app)


def test_assistant_response_includes_source_state_details():
    client = _client()

    fake_result = _FakeAskResult(
        answer="I found one stale file.",
        hits=[
            _FakeHit(
                chunk_id="stale:0",
                file_id="stale",
                chunk_index=0,
                file_path="/Users/test/Documents/old.txt",
                ext=".txt",
                text="old note",
                score=0.88,
                depth="deep",
            )
        ],
        query="what stale files do I have?",
    )

    with patch("api.v1.assistant.pipeline.ask", new=AsyncMock(return_value=fake_result)), \
         patch("api.v1.assistant.propose_from_hits", return_value=[]), \
         patch(
             "api.v1.assistant.get_indexed_state_map",
             return_value={
                 "stale": {
                     "file_state": "MISSING_EXTERNALLY",
                     "error_code": "MISSING_EXTERNALLY",
                     "error_message": "file no longer exists",
                 }
             },
             create=True,
         ):
        resp = client.post("/api/v1/assistant", json={"query": "what stale files do I have?"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["sources"] == ["/Users/test/Documents/old.txt"]
    assert len(body["source_details"]) == 1
    detail = body["source_details"][0]
    assert detail["file_id"] == "stale"
    assert detail["file_path"] == "/Users/test/Documents/old.txt"
    assert detail["file_state"] == "MISSING_EXTERNALLY"
    assert detail["error_code"] == "MISSING_EXTERNALLY"
    assert "no longer exists" in detail["error_message"]


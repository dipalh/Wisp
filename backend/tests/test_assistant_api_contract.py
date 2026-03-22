from __future__ import annotations

from dataclasses import dataclass, field
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


@pytest.mark.parametrize("file_state", ["MOVED_EXTERNALLY", "PERMISSION_DENIED", "LOCKED"])
def test_assistant_source_details_normalize_error_code_from_file_state(file_state):
    client = _client()

    fake_result = _FakeAskResult(
        answer="state answer",
        hits=[
            _FakeHit(
                chunk_id=f"{file_state.lower()}:0",
                file_id=file_state.lower(),
                chunk_index=0,
                file_path=f"/Users/test/Documents/{file_state.lower()}.txt",
                ext=".txt",
                text="state note",
                score=0.88,
                depth="deep",
            )
        ],
        query="state query",
    )

    with patch("api.v1.assistant.pipeline.ask", new=AsyncMock(return_value=fake_result)), \
         patch("api.v1.assistant.propose_from_hits", return_value=[]), \
         patch(
             "api.v1.assistant.get_indexed_state_map",
             return_value={
                 file_state.lower(): {
                     "file_state": file_state,
                     "error_code": "",
                     "error_message": "",
                 }
             },
             create=True,
         ):
        resp = client.post("/api/v1/assistant", json={"query": "state query"})

    assert resp.status_code == 200
    detail = resp.json()["source_details"][0]
    assert detail["file_state"] == file_state
    assert detail["error_code"] == file_state


def test_assistant_source_details_surface_stale_state_with_deterministic_message():
    client = _client()

    fake_result = _FakeAskResult(
        answer="state answer",
        hits=[
            _FakeHit(
                chunk_id="stale:0",
                file_id="stale",
                chunk_index=0,
                file_path="/Users/test/Documents/stale.txt",
                ext=".txt",
                text="stale note",
                score=0.88,
                depth="deep",
            )
        ],
        query="state query",
    )

    with patch("api.v1.assistant.pipeline.ask", new=AsyncMock(return_value=fake_result)), \
         patch("api.v1.assistant.propose_from_hits", return_value=[]), \
         patch(
             "api.v1.assistant.get_indexed_state_map",
             return_value={
                 "stale": {
                     "file_state": "STALE",
                     "error_code": "",
                     "error_message": "",
                 }
             },
             create=True,
         ):
        resp = client.post("/api/v1/assistant", json={"query": "state query"})

    assert resp.status_code == 200
    detail = resp.json()["source_details"][0]
    assert detail["file_state"] == "STALE"
    assert detail["error_code"] == "STALE"
    assert "STALE" in detail["error_message"]


def test_assistant_source_details_surface_quarantined_state_with_deterministic_message():
    client = _client()

    fake_result = _FakeAskResult(
        answer="state answer",
        hits=[
            _FakeHit(
                chunk_id="quarantined:0",
                file_id="quarantined",
                chunk_index=0,
                file_path="/Users/test/Documents/.wisp_quarantine/old.tmp",
                ext=".tmp",
                text="quarantined note",
                score=0.88,
                depth="deep",
            )
        ],
        query="state query",
    )

    with patch("api.v1.assistant.pipeline.ask", new=AsyncMock(return_value=fake_result)), \
         patch("api.v1.assistant.propose_from_hits", return_value=[]), \
         patch(
             "api.v1.assistant.get_indexed_state_map",
             return_value={
                 "quarantined": {
                     "file_state": "QUARANTINED",
                     "error_code": "",
                     "error_message": "",
                 }
             },
             create=True,
         ):
        resp = client.post("/api/v1/assistant", json={"query": "state query"})

    assert resp.status_code == 200
    detail = resp.json()["source_details"][0]
    assert detail["file_state"] == "QUARANTINED"
    assert detail["error_code"] == "QUARANTINED"
    assert (
        detail["error_message"]
        == "QUARANTINED: File is in quarantine and excluded from active indexing."
    )

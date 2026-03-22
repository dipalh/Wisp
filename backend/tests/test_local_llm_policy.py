from __future__ import annotations

import asyncio

from services.embedding.store import SearchHit


def test_local_ollama_policy_defaults():
    """LLM defaults must be local Ollama + qwen2.5:14b."""
    from ai import client

    assert client.MODEL_NAME == "qwen2.5:14b"
    assert client.OLLAMA_BASE_URL == "http://localhost:11434"


def test_search_flow_uses_local_ollama_embeddings(monkeypatch):
    """Search flow must embed through local Ollama, never external APIs."""
    from services.embedding import pipeline

    calls: list[tuple[str, dict]] = []

    def _fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"data": [{"embedding": [0.1] * 3072}]}

    monkeypatch.setattr("ai.embed._post_ollama_json", _fake_post, raising=False)
    monkeypatch.setattr(pipeline.store, "query", lambda *args, **kwargs: [])

    pipeline.search("find notes", k=1)

    assert calls, "expected embedding request to hit Ollama"
    path, payload = calls[0]
    assert path == "/v1/embeddings"
    assert payload["model"] == "qwen2.5:14b"


def test_assistant_flow_uses_local_ollama_chat(monkeypatch):
    """Assistant flow must generate responses through local Ollama chat completions."""
    from services.embedding import pipeline

    async def _fake_search(*args, **kwargs):
        return [
            SearchHit(
                chunk_id="doc:0",
                file_id="doc",
                chunk_index=0,
                file_path="/Users/test/doc.txt",
                ext=".txt",
                text="hello world",
                score=0.91,
                depth="deep",
            )
        ]

    calls: list[tuple[str, dict]] = []

    def _fake_post(path: str, payload: dict) -> dict:
        calls.append((path, payload))
        return {"choices": [{"message": {"content": "Local answer"}}]}

    monkeypatch.setattr(pipeline, "_search_async", _fake_search)
    monkeypatch.setattr("ai.generate._post_ollama_json", _fake_post, raising=False)

    result = asyncio.run(pipeline.ask("what is in doc?", k=1, auto_deepen=False))

    assert result.answer == "Local answer"
    assert calls, "expected chat completion request to hit Ollama"
    path, payload = calls[0]
    assert path == "/v1/chat/completions"
    assert payload["model"] == "qwen2.5:14b"


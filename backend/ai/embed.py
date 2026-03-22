from __future__ import annotations

import httpx

from ai.client import MODEL_NAME, get_ollama_base_url

_EMBED_PATH = "/v1/embeddings"


def _post_ollama_json(path: str, payload: dict) -> dict:
    url = f"{get_ollama_base_url()}{path}"
    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


def _extract_embeddings(response_json: dict) -> list[list[float]]:
    data = response_json.get("data")
    if not isinstance(data, list):
        raise RuntimeError("Ollama embedding response missing data list")
    embeddings: list[list[float]] = []
    for row in data:
        embedding = row.get("embedding") if isinstance(row, dict) else None
        if not isinstance(embedding, list):
            raise RuntimeError("Ollama embedding response has invalid embedding payload")
        embeddings.append([float(v) for v in embedding])
    return embeddings


def embed_text(text: str) -> list[float]:
    """Embed a single string through local Ollama."""
    payload = {"model": MODEL_NAME, "input": text}
    response_json = _post_ollama_json(_EMBED_PATH, payload)
    return _extract_embeddings(response_json)[0]


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings through local Ollama."""
    if not texts:
        return []
    payload = {"model": MODEL_NAME, "input": texts}
    response_json = _post_ollama_json(_EMBED_PATH, payload)
    return _extract_embeddings(response_json)


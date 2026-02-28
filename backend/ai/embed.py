from ai.client import EMBED_MODEL, get_client


def embed_text(text: str) -> list[float]:
    """Embed a single string. Returns a float vector."""
    client = get_client()
    result = client.models.embed_content(model=EMBED_MODEL, contents=text)
    return result.embeddings[0].values


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings. Automatically batches in groups of 100
    (the Gemini API limit per request). Returns a list of float vectors."""
    client = get_client()
    all_embeddings: list[list[float]] = []
    BATCH_SIZE = 100
    for i in range(0, len(texts), BATCH_SIZE):
        chunk = texts[i : i + BATCH_SIZE]
        result = client.models.embed_content(model=EMBED_MODEL, contents=chunk)
        all_embeddings.extend(e.values for e in result.embeddings)
    return all_embeddings

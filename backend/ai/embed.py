from ai.client import EMBED_MODEL, get_client


def embed_text(text: str) -> list[float]:
    """Embed a single string. Returns a float vector."""
    client = get_client()
    result = client.models.embed_content(model=EMBED_MODEL, contents=text)
    return result.embeddings[0].values


def embed_batch(texts: list[str]) -> list[list[float]]:
    """Embed a list of strings in one API call. Returns a list of float vectors."""
    client = get_client()
    result = client.models.embed_content(model=EMBED_MODEL, contents=texts)
    return [e.values for e in result.embeddings]

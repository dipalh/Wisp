from __future__ import annotations

import os
from urllib.parse import urlparse

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")


def _is_local_hostname(hostname: str | None) -> bool:
    if not hostname:
        return False
    return hostname in {"localhost", "127.0.0.1", "::1"}


def get_ollama_base_url() -> str:
    """Return a validated local-only Ollama URL.

    Privacy requirement: inference endpoints must be local-only.
    """
    parsed = urlparse(OLLAMA_BASE_URL)
    if parsed.scheme not in {"http", "https"} or not _is_local_hostname(parsed.hostname):
        raise RuntimeError(
            "OLLAMA_BASE_URL must point to localhost (privacy policy). "
            f"Got: {OLLAMA_BASE_URL}"
        )
    return OLLAMA_BASE_URL.rstrip("/")

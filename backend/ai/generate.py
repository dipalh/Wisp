from __future__ import annotations

import asyncio
import base64
import json
from typing import Type, TypeVar

import httpx
from pydantic import BaseModel

from ai.client import MODEL_NAME, get_ollama_base_url

T = TypeVar("T", bound=BaseModel)

_CHAT_PATH = "/v1/chat/completions"


def _post_ollama_json(path: str, payload: dict) -> dict:
    url = f"{get_ollama_base_url()}{path}"
    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


def _extract_chat_content(response_json: dict) -> str:
    choices = response_json.get("choices") or []
    if not choices:
        raise RuntimeError("Ollama response missing choices")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise RuntimeError("Ollama response missing assistant content")
    return content


async def generate_text(prompt: str, system: str | None = None) -> str:
    """Send a text prompt to local Ollama and return the response."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})

    payload = {
        "model": MODEL_NAME,
        "messages": messages,
        "temperature": 0.1,
    }
    response_json = await asyncio.to_thread(_post_ollama_json, _CHAT_PATH, payload)
    return _extract_chat_content(response_json).strip()


def _decode_file_preview(file_bytes: bytes, mime_type: str) -> str:
    if mime_type.startswith("text/") or mime_type in {
        "application/json",
        "application/xml",
        "application/javascript",
    }:
        return file_bytes[:8000].decode("utf-8", errors="replace")
    return ""


def _build_file_context(file_bytes: bytes, mime_type: str, ext: str) -> str:
    preview = _decode_file_preview(file_bytes, mime_type)
    if preview:
        return (
            f"File metadata: mime={mime_type}, ext={ext}, bytes={len(file_bytes)}.\n"
            "File preview:\n"
            f"{preview}"
        )

    encoded = base64.b64encode(file_bytes[:2048]).decode("ascii")
    return (
        f"File metadata: mime={mime_type}, ext={ext}, bytes={len(file_bytes)}.\n"
        "Binary sample (base64, truncated):\n"
        f"{encoded}"
    )


async def generate_with_file(
    prompt: str,
    file_bytes: bytes,
    mime_type: str,
    ext: str,
    force_files_api: bool = False,
) -> str:
    """Local-only file prompt generation via Ollama chat completions.

    force_files_api is kept for compatibility with existing call sites.
    """
    del force_files_api
    context = _build_file_context(file_bytes, mime_type, ext)
    full_prompt = f"{prompt}\n\n{context}"
    return await generate_text(full_prompt)


async def infer_from_filename(filename: str) -> str:
    return await generate_text(
        f"Given only the filename '{filename}', write a concise 1-2 sentence "
        "description of what this file most likely contains and its purpose. "
        "Be specific: mention the subject, document type, and likely contents."
    )


def _extract_json_object(text: str) -> str:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return text
    return text[start : end + 1]


async def generate_structured(
    prompt: str,
    schema: Type[T],
    system: str | None = None,
) -> T:
    schema_text = json.dumps(schema.model_json_schema(), ensure_ascii=True)
    structured_prompt = (
        f"{prompt}\n\n"
        "Return ONLY valid JSON that matches this JSON Schema:\n"
        f"{schema_text}"
    )
    raw = await generate_text(structured_prompt, system=system)
    return schema.model_validate_json(_extract_json_object(raw))


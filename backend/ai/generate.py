import asyncio
import os
import tempfile
from typing import Type, TypeVar

from google.genai import types
from pydantic import BaseModel

from ai.client import MODEL_NAME, get_client

T = TypeVar("T", bound=BaseModel)

INLINE_SIZE_LIMIT = 15 * 1024 * 1024  # 15 MB


async def generate_text(prompt: str, system: str | None = None) -> str:
    """Send a plain text prompt to Gemini and return the response."""
    client = get_client()
    config = types.GenerateContentConfig(system_instruction=system) if system else None
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=MODEL_NAME,
        contents=prompt,
        config=config,
    )
    return response.text


async def generate_with_file(
    prompt: str,
    file_bytes: bytes,
    mime_type: str,
    ext: str,
    force_files_api: bool = False,
) -> str:
    """Send a prompt + file to Gemini and return the response.

    Uses inline data for files under 15 MB; falls back to the Files API for
    larger files or when force_files_api=True (e.g. video).
    """
    client = get_client()

    if not force_files_api and len(file_bytes) <= INLINE_SIZE_LIMIT:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=MODEL_NAME,
            contents=[
                prompt,
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
            ],
        )
    else:
        response = await asyncio.to_thread(
            _via_files_api, client, file_bytes, mime_type, ext, prompt
        )

    return response.text


def _via_files_api(client, file_bytes: bytes, mime_type: str, ext: str, prompt: str):
    tmp_path = None
    uploaded = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        uploaded = client.files.upload(
            path=tmp_path,
            config=types.UploadFileConfig(mime_type=mime_type),
        )
        return client.models.generate_content(
            model=MODEL_NAME,
            contents=[prompt, uploaded],
        )
    finally:
        if tmp_path:
            os.unlink(tmp_path)
        if uploaded:
            client.files.delete(name=uploaded.name)


async def infer_from_filename(filename: str) -> str:
    """Infer semantic meaning of a file from its filename alone.

    Used when content extraction is impractical (file too large, unsupported
    type, or binary blob). Accurate enough for directory organisation and search
    indexing — especially for descriptively-named academic and work files.
    """
    return await generate_text(
        f"Given only the filename '{filename}', write a concise 1-2 sentence "
        f"description of what this file most likely contains and its purpose. "
        f"Be specific: mention the subject, document type, and likely contents. "
        f"Do not hedge — commit to the most probable interpretation."
    )


async def generate_structured(
    prompt: str,
    schema: Type[T],
    system: str | None = None,
) -> T:
    """Call Gemini in JSON mode and return a validated Pydantic instance.

    Uses Gemini's structured output feature (response_schema) to guarantee the
    response conforms to the provided Pydantic model.

    Args:
        prompt: The user-role prompt to send.
        schema: A Pydantic BaseModel subclass describing the desired output shape.
        system: Optional system instruction.

    Returns:
        A validated instance of ``schema``.
    """
    client = get_client()
    config = types.GenerateContentConfig(
        response_mime_type="application/json",
        response_schema=schema,
        system_instruction=system,
    )
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=MODEL_NAME,
        contents=prompt,
        config=config,
    )
    # SDK populates response.parsed when response_schema is a Pydantic model
    if hasattr(response, "parsed") and response.parsed is not None:
        return response.parsed
    return schema.model_validate_json(response.text)

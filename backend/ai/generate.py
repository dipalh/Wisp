import asyncio
import os
import tempfile

from google.genai import types

from ai.client import MODEL_NAME, get_client

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

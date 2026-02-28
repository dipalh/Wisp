import os
import tempfile

from google.genai import types

from services.file_processor.client import MODEL_NAME, get_client

INLINE_SIZE_LIMIT = 15 * 1024 * 1024  # 15 MB

_PROMPTS: dict[str, str] = {
    "image": (
        "Describe all visible content in this image comprehensively: "
        "every piece of text, objects, diagrams, charts, and their context. "
        "Return as plain text only."
    ),
    "video": (
        "Transcribe all spoken content and describe the key visual scenes, "
        "events, and any on-screen text in this video. "
        "Return as plain text only."
    ),
    "audio": (
        "Transcribe all spoken content from this audio file. "
        "Note any speaker changes, music, or notable audio events. "
        "Return as plain text only."
    ),
    "document": (
        "Extract all text from this document exactly as it appears, "
        "preserving layout and structure. Return only the extracted text."
    ),
}


def _prompt_for(mime_type: str) -> str:
    category = mime_type.split("/")[0]
    return _PROMPTS.get(category, _PROMPTS["document"])


async def extract(
    file_bytes: bytes,
    mime_type: str,
    ext: str,
    force_files_api: bool = False,
) -> str:
    client = get_client()
    prompt = _prompt_for(mime_type)

    if not force_files_api and len(file_bytes) <= INLINE_SIZE_LIMIT:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                prompt,
                types.Part.from_bytes(data=file_bytes, mime_type=mime_type),
            ],
        )
    else:
        response = _via_files_api(client, file_bytes, mime_type, ext, prompt)

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

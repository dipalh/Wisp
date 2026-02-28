import base64
import os
import tempfile

import google.generativeai as genai

from services.file_processor.client import get_model

INLINE_SIZE_LIMIT = 15 * 1024 * 1024  # 15 MB

# Per-category prompts tuned for vector DB ingestion
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
    category = mime_type.split("/")[0]  # "image", "video", "audio", "application", "text"
    if category in _PROMPTS:
        return _PROMPTS[category]
    return _PROMPTS["document"]


async def extract(
    file_bytes: bytes,
    mime_type: str,
    ext: str,
    force_files_api: bool = False,
) -> str:
    model = get_model()
    prompt = _prompt_for(mime_type)

    if not force_files_api and len(file_bytes) <= INLINE_SIZE_LIMIT:
        response = _inline(model, file_bytes, mime_type, prompt)
    else:
        response = _via_files_api(model, file_bytes, mime_type, ext, prompt)

    return response.text


def _inline(
    model: genai.GenerativeModel,
    file_bytes: bytes,
    mime_type: str,
    prompt: str,
) -> genai.types.GenerateContentResponse:
    part = {
        "inline_data": {
            "mime_type": mime_type,
            "data": base64.b64encode(file_bytes).decode(),
        }
    }
    return model.generate_content([prompt, part])


def _via_files_api(
    model: genai.GenerativeModel,
    file_bytes: bytes,
    mime_type: str,
    ext: str,
    prompt: str,
) -> genai.types.GenerateContentResponse:
    tmp_path = None
    uploaded = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name
        uploaded = genai.upload_file(tmp_path, mime_type=mime_type)
        return model.generate_content([prompt, uploaded])
    finally:
        if tmp_path:
            os.unlink(tmp_path)
        if uploaded:
            genai.delete_file(uploaded.name)

from ai.generate import generate_with_file

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
    return await generate_with_file(
        _prompt_for(mime_type), file_bytes, mime_type, ext, force_files_api
    )

import base64
import os
import tempfile
from pathlib import Path

import google.generativeai as genai

from services.google_ocr.client import get_model
from services.google_ocr.models import OCRResult

# Files larger than this are uploaded via the Files API instead of sent inline
INLINE_SIZE_LIMIT = 15 * 1024 * 1024  # 15 MB

MIME_TYPES: dict[str, str] = {
    ".pdf": "application/pdf",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
}

OCR_PROMPT = (
    "Extract all text from this document or image exactly as it appears. "
    "Preserve the original layout, line breaks, and structure as closely as possible. "
    "Return only the extracted text with no commentary."
)


async def extract_text(file_bytes: bytes, filename: str) -> OCRResult:
    ext = Path(filename).suffix.lower()
    mime_type = MIME_TYPES.get(ext)

    if not mime_type:
        raise ValueError(f"Unsupported file type '{ext}'. Supported: {', '.join(MIME_TYPES)}")

    model = get_model()

    if len(file_bytes) <= INLINE_SIZE_LIMIT:
        response = _extract_inline(model, file_bytes, mime_type)
    else:
        response = _extract_via_files_api(model, file_bytes, mime_type, ext)

    return OCRResult(
        filename=filename,
        mime_type=mime_type,
        extracted_text=response.text,
    )


def _extract_inline(
    model: genai.GenerativeModel, file_bytes: bytes, mime_type: str
) -> genai.types.GenerateContentResponse:
    part = {
        "inline_data": {
            "mime_type": mime_type,
            "data": base64.b64encode(file_bytes).decode(),
        }
    }
    return model.generate_content([OCR_PROMPT, part])


def _extract_via_files_api(
    model: genai.GenerativeModel, file_bytes: bytes, mime_type: str, ext: str
) -> genai.types.GenerateContentResponse:
    """Upload to Gemini Files API for files > 15 MB, then delete after use."""
    tmp_path = None
    uploaded_file = None
    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        uploaded_file = genai.upload_file(tmp_path, mime_type=mime_type)
        return model.generate_content([OCR_PROMPT, uploaded_file])
    finally:
        if tmp_path:
            os.unlink(tmp_path)
        if uploaded_file:
            genai.delete_file(uploaded_file.name)

from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from services.google_ocr.models import OCRResult
from services.google_ocr.processor import MIME_TYPES, extract_text

router = APIRouter()

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB


@router.post("/", response_model=OCRResult, summary="Extract text from a PDF or image")
async def ocr(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Accepted: {', '.join(MIME_TYPES)}",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds the 50 MB limit.")

    try:
        return await extract_text(file_bytes, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {e}")

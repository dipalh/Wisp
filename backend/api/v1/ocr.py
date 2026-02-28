from pathlib import Path

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile

from services.cloud_ocr.models import OCRResult
from services.cloud_ocr.processor import SUPPORTED_EXTENSIONS, extract_text

router = APIRouter()

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB — Cloud Vision synchronous limit


@router.post("/", response_model=OCRResult, summary="Extract text from an image using Google Cloud Vision")
async def ocr(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported type '{ext}'. Accepted: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds the 20 MB limit.")

    try:
        return await extract_text(file_bytes, file.filename)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Cloud Vision request failed: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"OCR failed: {e}")

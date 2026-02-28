from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from services.file_processor.dispatcher import ALL_MIME_TYPES, extract
from services.file_processor.models import ContentResult

router = APIRouter()

MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


@router.post("/", response_model=ContentResult, summary="Extract content from any file for vector DB ingestion")
async def extract_content(file: UploadFile = File(...)):
    ext = Path(file.filename).suffix.lower()
    if ext not in ALL_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. Accepted: {', '.join(sorted(ALL_MIME_TYPES))}",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds the 100 MB limit.")

    try:
        return await extract(file_bytes, file.filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extraction failed: {e}")

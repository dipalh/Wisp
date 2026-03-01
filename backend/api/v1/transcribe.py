from pathlib import Path

import httpx
from fastapi import APIRouter, File, HTTPException, UploadFile

from services.transcribe.models import TranscriptResult
from services.transcribe.transcriber import SUPPORTED_EXTENSIONS, transcribe

router = APIRouter()

MAX_FILE_SIZE = 500 * 1024 * 1024  # 500 MB


@router.post("/", response_model=TranscriptResult, summary="Transcribe audio or video via ElevenLabs Scribe")
async def transcribe_audio(file: UploadFile = File(...)):
    ext = Path(file.filename or "").suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported type '{ext}'. Accepted: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File exceeds the 500 MB limit.")

    try:
        return await transcribe(file_bytes, file.filename or "audio")
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"ElevenLabs Scribe error: HTTP {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Transcription failed: {e}")

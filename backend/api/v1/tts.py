import io

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services.tts.speaker import DEFAULT_VOICE_ID, speak

router = APIRouter()


class TTSRequest(BaseModel):
    text: str
    voice_id: str = DEFAULT_VOICE_ID


@router.post("/", summary="Convert text to speech via ElevenLabs")
async def text_to_speech(req: TTSRequest):
    if not req.text.strip():
        raise HTTPException(status_code=422, detail="text must not be empty")
    try:
        audio = await speak(req.text, req.voice_id)
        return StreamingResponse(io.BytesIO(audio), media_type="audio/mpeg")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"TTS failed: {e}")

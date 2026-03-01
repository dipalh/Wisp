import httpx

from config import ELEVENLABS_API_KEY
from services.transcribe.models import TranscriptResult, TranscriptSegment

_ENDPOINT = "https://api.elevenlabs.io/v1/speech-to-text"

SUPPORTED_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".ogg", ".flac", ".aac", ".opus",
    ".mp4", ".mov", ".webm", ".mkv",
}


async def transcribe(audio_bytes: bytes, filename: str) -> TranscriptResult:
    if not ELEVENLABS_API_KEY:
        raise RuntimeError("ELEVENLABS_API_KEY is not configured in .env")

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            _ENDPOINT,
            headers={"xi-api-key": ELEVENLABS_API_KEY},
            files={"file": (filename, audio_bytes, "application/octet-stream")},
            data={"model_id": "scribe_v1", "diarize": "true"},
        )
        response.raise_for_status()

    data = response.json()
    words = data.get("words", [])
    full_text = data.get("text", "")

    # Group consecutive words by speaker into segments
    segments: list[TranscriptSegment] = []
    current_speaker: str | None = None
    current_words: list[str] = []

    for w in words:
        if w.get("type") != "word":
            continue
        speaker = w.get("speaker_id", "speaker_0")
        if speaker != current_speaker:
            if current_words and current_speaker is not None:
                segments.append(TranscriptSegment(
                    speaker=current_speaker,
                    text=" ".join(current_words),
                ))
            current_speaker = speaker
            current_words = [w["text"]]
        else:
            current_words.append(w["text"])

    if current_words:
        segments.append(TranscriptSegment(
            speaker=current_speaker or "speaker_0",
            text=" ".join(current_words),
        ))

    unique_speakers = len({s.speaker for s in segments})
    word_count = len([w for w in words if w.get("type") == "word"])

    return TranscriptResult(
        text=full_text,
        language=data.get("language_code", "unknown"),
        language_probability=round(data.get("language_probability", 0.0), 4),
        word_count=word_count,
        char_count=len(full_text),
        speakers=unique_speakers,
        segments=segments,
    )

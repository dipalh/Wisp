import asyncio

from elevenlabs import VoiceSettings
from elevenlabs.client import ElevenLabs

from config import ELEVENLABS_API_KEY

# Adam — deep, authoritative (Jarvis-like). Swap for any ElevenLabs voice ID.
DEFAULT_VOICE_ID = "pNInz6obpgDQGcFmaJgB"
MODEL_ID = "eleven_turbo_v2_5"  # lowest latency, best for real-time conversation


def _synthesize(text: str, voice_id: str) -> bytes:
    if not ELEVENLABS_API_KEY:
        raise ValueError("ELEVENLABS_API_KEY is not set in .env")
    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
    chunks = client.text_to_speech.convert(
        voice_id=voice_id,
        text=text,
        model_id=MODEL_ID,
        voice_settings=VoiceSettings(stability=0.5, similarity_boost=0.75),
        output_format="mp3_44100_128",
    )
    return b"".join(chunks)


async def speak(text: str, voice_id: str = DEFAULT_VOICE_ID) -> bytes:
    """Convert text to speech. Returns raw MP3 bytes."""
    return await asyncio.to_thread(_synthesize, text, voice_id)


async def list_voices() -> list[dict]:
    """Return available ElevenLabs voices (English only)."""
    if not ELEVENLABS_API_KEY:
        return []
    def _get():
        client = ElevenLabs(api_key=ELEVENLABS_API_KEY)
        resp = client.voices.get_all()
        voices = []
        for v in resp.voices:
            labels = getattr(v, "labels", {}) or {}
            if not isinstance(labels, dict):
                labels = {}
            language = labels.get("language", "en")
            if language != "en":
                continue
            voices.append({
                "voice_id": v.voice_id,
                "name": v.name,
                "category": getattr(v, "category", None),
                "preview_url": getattr(v, "preview_url", None),
                "language": language,
                "accent": labels.get("accent", ""),
            })
        return voices
    return await asyncio.to_thread(_get)

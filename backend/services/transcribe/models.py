from pydantic import BaseModel


class TranscriptSegment(BaseModel):
    speaker: str
    text: str


class TranscriptResult(BaseModel):
    text: str
    language: str
    language_probability: float
    word_count: int
    char_count: int
    speakers: int
    segments: list[TranscriptSegment]

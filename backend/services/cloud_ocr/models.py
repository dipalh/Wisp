from pydantic import BaseModel


class OCRResult(BaseModel):
    filename: str
    text: str           # full extracted text
    confidence: float   # average confidence across all blocks (0.0–1.0)

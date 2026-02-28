from pydantic import BaseModel


class OCRResult(BaseModel):
    filename: str
    mime_type: str
    extracted_text: str

from pydantic import BaseModel


class ContentResult(BaseModel):
    filename: str
    mime_type: str
    content: str  # extracted text / description — ready for chunking + embedding

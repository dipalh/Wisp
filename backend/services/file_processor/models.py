from pydantic import BaseModel, Field


class ContentResult(BaseModel):
    filename: str
    file_name: str
    mime_type: str
    category: str
    content: str  # extracted text / description — ready for chunking + embedding
    text: str
    engine_used: str = "real"
    fallback_used: bool = False
    errors: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

from pydantic import BaseModel

CATEGORIES = ["School", "Work", "Legal", "Receipts", "Media", "Code", "Personal", "Unsorted"]
CONFIDENCE_THRESHOLD = 0.75


class ClassificationResult(BaseModel):
    category: str        # one of CATEGORIES
    tags: list[str]      # semantic tags to keep in DB
    confidence: float    # 0.0 (no idea) → 1.0 (certain)

import base64

import httpx

from config import GOOGLE_CLOUD_VISION_API_KEY
from services.cloud_ocr.models import OCRResult

_ENDPOINT = "https://vision.googleapis.com/v1/images:annotate"

SUPPORTED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".ico", ".tiff", ".tif",
}


async def extract_text(image_bytes: bytes, filename: str) -> OCRResult:
    if not GOOGLE_CLOUD_VISION_API_KEY:
        raise RuntimeError("GOOGLE_CLOUD_VISION_API_KEY is not configured")

    payload = {
        "requests": [{
            "image": {"content": base64.b64encode(image_bytes).decode()},
            "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
        }]
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            _ENDPOINT,
            params={"key": GOOGLE_CLOUD_VISION_API_KEY},
            json=payload,
        )
        response.raise_for_status()

    data = response.json()
    result = data["responses"][0]

    if "error" in result:
        err = result["error"]
        raise RuntimeError(f"Cloud Vision API error: {err.get('message')} (code {err.get('code')})")

    annotation = result.get("fullTextAnnotation", {})
    full_text = annotation.get("text", "")

    # Compute average word confidence across all pages
    confidences: list[float] = []
    for page in annotation.get("pages", []):
        for block in page.get("blocks", []):
            for paragraph in block.get("paragraphs", []):
                for word in paragraph.get("words", []):
                    conf = word.get("confidence")
                    if conf is not None:
                        confidences.append(conf)

    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    return OCRResult(
        filename=filename,
        text=full_text,
        confidence=round(avg_confidence, 4),
    )

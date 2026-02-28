from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1.ocr import router as ocr_router

app = FastAPI(title="Wisp OCR API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ocr_router, prefix="/api/v1/ocr", tags=["OCR"])


@app.get("/health")
async def health():
    return {"status": "ok"}

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1.extract import router as extract_router
from api.v1.ocr import router as ocr_router
from api.v1.organize import router as organize_router
from api.v1.tts import router as tts_router

app = FastAPI(title="Wisp API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(extract_router, prefix="/api/v1/extract", tags=["Extract"])
app.include_router(ocr_router, prefix="/api/v1/ocr", tags=["OCR"])
app.include_router(tts_router, prefix="/api/v1/tts", tags=["TTS"])
app.include_router(organize_router, prefix="/api/v1/organize", tags=["Organize"])


@app.get("/health")
async def health():
    return {"status": "ok"}

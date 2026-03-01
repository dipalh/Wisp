from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1.actions import router as actions_router
from api.v1.extract import router as extract_router
from api.v1.ingest import router as ingest_router
from api.v1.ocr import router as ocr_router
from api.v1.organize import router as organize_router
from api.v1.assistant import router as assistant_router
from api.v1.roots import router as roots_router
from api.v1.scan import router as scan_router
from api.v1.search import router as search_router
from api.v1.tts import router as tts_router
from api.v1.transcribe import router as transcribe_router
from api.v1.debloat import router as debloat_router
import uvicorn

app = FastAPI(title="Wisp API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Flow 1: Scan / Index
app.include_router(roots_router, prefix="/api/v1/roots",  tags=["Roots"])
app.include_router(scan_router,  prefix="/api/v1/scan",   tags=["Scan"])

# Flow 2: Search
app.include_router(search_router, prefix="/api/v1/search", tags=["Search"])

# Flow 3: Assistant / Propose / Execute
app.include_router(assistant_router, prefix="/api/v1/assistant", tags=["Assistant"])

# Existing endpoints
app.include_router(extract_router,  prefix="/api/v1/extract",  tags=["Extract"])
app.include_router(ocr_router,         prefix="/api/v1/ocr",         tags=["OCR"])
app.include_router(tts_router,         prefix="/api/v1/tts",         tags=["TTS"])
app.include_router(transcribe_router,  prefix="/api/v1/transcribe",  tags=["Transcribe"])
app.include_router(organize_router, prefix="/api/v1/organize",  tags=["Organize"])
app.include_router(ingest_router,   prefix="/api/v1/ingest",    tags=["Ingest"])
app.include_router(actions_router,  prefix="/api/v1/actions",   tags=["Actions"])
app.include_router(debloat_router,  prefix="/api/v1/debloat",   tags=["Debloat"])


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

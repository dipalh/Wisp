import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.v1.actions import router as actions_router
from api.v1.extract import router as extract_router
from api.v1.ingest import router as ingest_router
from api.v1.ocr import router as ocr_router
from api.v1.organize import router as organize_router
from api.v1.assistant import router as assistant_router
from api.v1.roots import router as roots_router
from api.v1.search import router as search_router
from api.v1.debloat import router as debloat_router
from api.v1.jobs import router as jobs_router
from services.embedding import store
import uvicorn

logger = logging.getLogger(__name__)

try:
    from api.v1.tts import router as tts_router
    _HAS_TTS = True
except ImportError:
    _HAS_TTS = False
    logger.warning("elevenlabs not installed — TTS endpoints disabled")

try:
    from api.v1.transcribe import router as transcribe_router
    _HAS_TRANSCRIBE = True
except ImportError:
    _HAS_TRANSCRIBE = False
    logger.warning("Transcribe dependencies missing — transcribe endpoints disabled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initialising LanceDB store …")
    store.init()
    logger.info("LanceDB store ready at %s", store._db_path)
    yield
    logger.info("Shutting down LanceDB store …")
    store.teardown()


app = FastAPI(title="Wisp API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Flow 1: Scan / Index
app.include_router(roots_router, prefix="/api/v1/roots",  tags=["Roots"])

# Flow 2: Search
app.include_router(search_router, prefix="/api/v1/search", tags=["Search"])

# Flow 3: Assistant / Propose / Execute
app.include_router(assistant_router, prefix="/api/v1/assistant", tags=["Assistant"])

# Existing endpoints
app.include_router(extract_router,  prefix="/api/v1/extract",  tags=["Extract"])
app.include_router(ocr_router,         prefix="/api/v1/ocr",         tags=["OCR"])
if _HAS_TTS:
    app.include_router(tts_router,         prefix="/api/v1/tts",         tags=["TTS"])
if _HAS_TRANSCRIBE:
    app.include_router(transcribe_router,  prefix="/api/v1/transcribe",  tags=["Transcribe"])
app.include_router(organize_router, prefix="/api/v1/organize",  tags=["Organize"])
app.include_router(ingest_router,   prefix="/api/v1/ingest",    tags=["Ingest"])
app.include_router(actions_router,  prefix="/api/v1/actions",   tags=["Actions"])
app.include_router(debloat_router,  prefix="/api/v1/debloat",   tags=["Debloat"])
app.include_router(jobs_router,     prefix="/api/v1/jobs",      tags=["Jobs"])


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

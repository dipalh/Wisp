from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.v1.extract import router as extract_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(extract_router, prefix="/api/v1/extract")
    return TestClient(app)


def test_extract_txt_returns_canonical_contract_with_metadata():
    client = _client()
    payload = b"hello world\nline two\n"

    resp = client.post(
        "/api/v1/extract/",
        files={"file": ("hello.txt", payload, "text/plain")},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["file_name"] == "hello.txt"
    assert body["mime_type"] == "text/plain"
    assert body["category"] == "text"
    assert body["text"] == "hello world\nline two\n"
    assert body["engine_used"] == "local"
    assert body["fallback_used"] is False
    assert body["errors"] == []
    assert body["metadata"] == {"size_bytes": len(payload), "ext": ".txt"}


def test_extract_docx_uses_local_office_path_with_canonical_contract():
    client = _client()
    payload = b"fake-docx-bytes"

    with patch("services.file_processor.dispatcher.office.extract", return_value="hello docx"):
        resp = client.post(
            "/api/v1/extract/",
            files={
                "file": (
                    "sample.docx",
                    payload,
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["file_name"] == "sample.docx"
    assert body["category"] == "office"
    assert body["text"] == "hello docx"
    assert body["engine_used"] == "local"
    assert body["fallback_used"] is False
    assert body["errors"] == []
    assert body["metadata"] == {"size_bytes": len(payload), "ext": ".docx"}


def test_extract_gemini_failure_returns_deterministic_fake_payload():
    client = _client()
    payload = b"\x89PNG\r\n\x1a\n\x00"

    with patch("services.file_processor.dispatcher.gemini.extract", side_effect=RuntimeError("gemini down")):
        resp = client.post(
            "/api/v1/extract/",
            files={"file": ("image.png", payload, "image/png")},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["file_name"] == "image.png"
    assert body["category"] == "image"
    assert body["text"] == "DEMO_EXTRACT:png:image.png"
    assert body["engine_used"] == "fake"
    assert body["fallback_used"] is True
    assert body["errors"] == ["gemini extraction failed: gemini down"]
    assert body["metadata"] == {
        "size_bytes": len(payload),
        "ext": ".png",
        "family": "image",
        "mode": "fallback",
    }


def test_extract_unknown_extension_returns_safe_inferred_payload():
    from services.file_processor.dispatcher import extract

    payload = b"\xff\xfe\xfd\xfc"
    with patch("ai.generate.infer_from_filename", new=AsyncMock(return_value="Likely a binary artifact.")):
        result = asyncio.run(extract(payload, "mystery.weird"))

    assert result.engine_used == "filename-infer"
    assert result.fallback_used is False
    assert result.text == "Likely a binary artifact."
    assert result.errors == ["unsupported extension '.weird' inferred from filename"]
    assert result.metadata == {"size_bytes": len(payload), "ext": ".weird"}


def test_extract_pdf_contract_uses_pdf_family_category_and_metadata():
    client = _client()
    payload = b"%PDF-1.7 fake payload"

    with patch("services.file_processor.dispatcher.gemini.extract", new=AsyncMock(return_value="PDF summary")):
        resp = client.post(
            "/api/v1/extract/",
            files={"file": ("report.pdf", payload, "application/pdf")},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["file_name"] == "report.pdf"
    assert body["mime_type"] == "application/pdf"
    assert body["category"] == "pdf"
    assert body["text"] == "PDF summary"
    assert body["engine_used"] == "gemini"
    assert body["fallback_used"] is False
    assert body["errors"] == []
    assert body["metadata"] == {
        "size_bytes": len(payload),
        "ext": ".pdf",
        "family": "pdf",
        "mode": "gemini",
    }


def test_extract_image_contract_reports_image_family_metadata():
    client = _client()
    payload = b"\x89PNG\r\n\x1a\n\x00img"

    with patch("services.file_processor.dispatcher.gemini.extract", new=AsyncMock(return_value="Image caption")):
        resp = client.post(
            "/api/v1/extract/",
            files={"file": ("photo.png", payload, "image/png")},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["file_name"] == "photo.png"
    assert body["mime_type"] == "image/png"
    assert body["category"] == "image"
    assert body["text"] == "Image caption"
    assert body["engine_used"] == "gemini"
    assert body["fallback_used"] is False
    assert body["errors"] == []
    assert body["metadata"] == {
        "size_bytes": len(payload),
        "ext": ".png",
        "family": "image",
        "mode": "gemini",
    }


def test_extract_image_gemini_failure_reports_fallback_mode_metadata():
    client = _client()
    payload = b"\x89PNG\r\n\x1a\n\x00img"

    with patch("services.file_processor.dispatcher.gemini.extract", side_effect=RuntimeError("vision unavailable")):
        resp = client.post(
            "/api/v1/extract/",
            files={"file": ("photo.png", payload, "image/png")},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["engine_used"] == "fake"
    assert body["fallback_used"] is True
    assert body["errors"] == ["gemini extraction failed: vision unavailable"]
    assert body["metadata"] == {
        "size_bytes": len(payload),
        "ext": ".png",
        "family": "image",
        "mode": "fallback",
    }


def test_extract_archive_contract_reports_archive_metadata():
    client = _client()
    payload = b"PK\x03\x04fake-zip"

    with patch("services.file_processor.dispatcher.archive.extract", return_value="archive manifest"):
        resp = client.post(
            "/api/v1/extract/",
            files={"file": ("bundle.zip", payload, "application/zip")},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["file_name"] == "bundle.zip"
    assert body["mime_type"] == "application/zip"
    assert body["category"] == "archive"
    assert body["text"] == "archive manifest"
    assert body["engine_used"] == "local"
    assert body["fallback_used"] is False
    assert body["errors"] == []
    assert body["metadata"] == {"size_bytes": len(payload), "ext": ".zip", "family": "archive"}


def test_extract_binary_contract_reports_binary_metadata():
    client = _client()
    payload = b"MZ\x90\x00\x03\x00\x00\x00"

    with patch("services.file_processor.dispatcher.binary.extract", return_value="pe metadata"):
        resp = client.post(
            "/api/v1/extract/",
            files={"file": ("installer.exe", payload, "application/x-msdownload")},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["file_name"] == "installer.exe"
    assert body["mime_type"] == "application/x-msdownload"
    assert body["category"] == "binary"
    assert body["text"] == "pe metadata"
    assert body["engine_used"] == "local"
    assert body["fallback_used"] is False
    assert body["errors"] == []
    assert body["metadata"] == {"size_bytes": len(payload), "ext": ".exe", "family": "binary"}

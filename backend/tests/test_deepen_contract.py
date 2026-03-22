from __future__ import annotations

import asyncio
from unittest.mock import patch

from services.embedding import pipeline
from services.file_processor.models import ContentResult


def test_ingest_deep_uses_dispatcher_text_when_content_field_is_empty(tmp_path):
    target = tmp_path / "report.txt"
    target.write_text("placeholder")

    recorded: dict[str, str] = {}

    async def _fake_dispatch_extract(file_bytes: bytes, filename: str):
        return ContentResult(
            filename=filename,
            file_name=filename,
            mime_type="text/plain",
            category="text",
            content="",
            text="deep extraction payload from text field",
            engine_used="gemini",
            fallback_used=False,
            errors=[],
            metadata={"size_bytes": len(file_bytes), "ext": ".txt"},
        )

    async def _fake_ingest_async(cr: ContentResult, file_id: str, depth: str):
        recorded["depth"] = depth
        recorded["content"] = cr.content
        return pipeline.IngestResult(
            file_id=file_id,
            file_path=str(target),
            chunk_count=1,
            depth=depth,
            engine=cr.engine_used,
        )

    with patch("services.file_processor.dispatcher.extract", side_effect=_fake_dispatch_extract), \
         patch.object(pipeline, "_ingest_async", side_effect=_fake_ingest_async):
        result = asyncio.run(
            pipeline._ingest_deep(
                target,
                file_id="file-1",
                file_bytes=target.read_bytes(),
                ext=".txt",
                fp="",
            )
        )

    assert result.depth == "deep"
    assert recorded["depth"] == "deep"
    assert recorded["content"] == "deep extraction payload from text field"

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

from services.ingestor import ingester


class _FakePipeline:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = [("seed", "seed.txt", "seed content")]

    def ingest(self, cr, file_id: str) -> None:
        self.rows.append((file_id, cr.file_name, cr.text))


def test_unsupported_ingest_keeps_index_integrity_when_infer_fails(tmp_path):
    target = tmp_path / "mystery.weird"
    target.write_bytes(b"\xff\xfe\xfd")
    fake_pipeline = _FakePipeline()
    before = list(fake_pipeline.rows)

    with patch("ai.generate.infer_from_filename", new=AsyncMock(side_effect=RuntimeError("ollama unavailable"))):
        engine = asyncio.run(ingester.ingest_file(target, "mystery.weird", fake_pipeline))

    assert fake_pipeline.rows[0] == before[0]
    assert len(fake_pipeline.rows) == len(before) + 1
    assert fake_pipeline.rows[-1][1] == "mystery.weird"
    assert fake_pipeline.rows[-1][2] == "DEMO_EXTRACT:weird:mystery.weird"
    assert engine == "fake"

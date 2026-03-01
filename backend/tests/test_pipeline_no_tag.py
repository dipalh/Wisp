"""
Verify that pipeline.ingest_file() does NOT call set_deletable() or
should_mark_deletable().  OS tagging ownership belongs exclusively to
the Celery scan task, not the pipeline.

This prevents double-tagging races where the pipeline (with AI summary)
and task (without) reach different conclusions for the same file.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import pytest


@pytest.fixture(autouse=True)
def _mock_store():
    """Prevent real LanceDB init."""
    with patch("services.embedding.pipeline.store") as mock_store:
        mock_store.current_db_path.return_value = None
        mock_store.query.return_value = []
        yield mock_store


@pytest.fixture(autouse=True)
def _mock_embed():
    """Prevent real embedding calls."""
    with patch("services.embedding.pipeline.embed_batch") as mock_eb, \
         patch("services.embedding.pipeline.embed_text") as mock_et:
        mock_eb.return_value = [[0.1] * 768]
        mock_et.return_value = [0.1] * 768
        yield


def test_ingest_file_never_calls_set_deletable(tmp_path: Path):
    """pipeline.ingest_file must NOT call set_deletable — the task owns tagging."""
    test_file = tmp_path / "readme.txt"
    test_file.write_text("hello world")

    mock_set = MagicMock()
    mock_should = MagicMock()

    import asyncio
    from services.embedding.pipeline import ingest_file, init_store, teardown_store

    init_store()
    try:
        with patch("services.os_tags.deletable.set_deletable", mock_set), \
             patch("services.os_tags.deletable.should_mark_deletable", mock_should):
            result = asyncio.run(ingest_file(test_file))
    finally:
        teardown_store()

    mock_set.assert_not_called()
    mock_should.assert_not_called()


def test_ingest_file_card_only_never_calls_set_deletable(tmp_path: Path):
    """Card-only files (video/audio/archives) must also not trigger tagging."""
    test_file = tmp_path / "movie.mp4"
    test_file.write_bytes(b"\x00" * 100)

    mock_set = MagicMock()
    mock_should = MagicMock()

    import asyncio
    from services.embedding.pipeline import ingest_file, init_store, teardown_store

    init_store()
    try:
        with patch("services.os_tags.deletable.set_deletable", mock_set), \
             patch("services.os_tags.deletable.should_mark_deletable", mock_should):
            result = asyncio.run(ingest_file(test_file))
    finally:
        teardown_store()

    mock_set.assert_not_called()
    mock_should.assert_not_called()

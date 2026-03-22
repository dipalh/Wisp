from __future__ import annotations

import asyncio

import pytest
from pydantic import ValidationError

from services.organizer.models import DirectoryProposal
from services.organizer.suggester import suggest_directories


def test_organize_proposal_requires_citations_and_reasons():
    with pytest.raises(ValidationError):
        DirectoryProposal(
            name="By Project",
            rationale="Group files by shared project context.",
            folder_tree=["Projects/Alpha/"],
            mappings=[
                {
                    "original_path": "/tmp/root/report.txt",
                    "suggested_path": "Projects/Alpha/report.txt",
                }
            ],
        )


def test_organize_mock_mode_deterministic_for_same_fixture(monkeypatch):
    fixture_files = [
        {
            "file_path": "/workspace/root/docs/report.txt",
            "ext": ".txt",
            "text": "Quarterly report",
        },
        {
            "file_path": "/workspace/root/media/photo.png",
            "ext": ".png",
            "text": "Trip photo",
        },
    ]
    monkeypatch.setattr("services.organizer.suggester.store.list_files", lambda: fixture_files)

    first = asyncio.run(suggest_directories(mock_mode=True))
    second = asyncio.run(suggest_directories(mock_mode=True))

    assert first.model_dump() == second.model_dump()
    assert len(first.proposals) >= 1

from __future__ import annotations

import pytest

from services.organizer.tool_router import OrganizerToolRouter


def test_semantic_search_contract():
    router = OrganizerToolRouter()
    with pytest.raises(ValueError, match="query must be non-empty"):
        router.semantic_search("", limit=5)
    results = router.semantic_search("invoice", limit=2)
    assert isinstance(results, list)
    assert len(results) <= 2


def test_get_preview_contract(tmp_path):
    router = OrganizerToolRouter()
    target = tmp_path / "doc.txt"
    target.write_text("hello world")
    with pytest.raises(ValueError, match="path must be non-empty"):
        router.get_preview("")
    preview = router.get_preview(str(target), max_chars=5)
    assert preview["path"] == str(target)
    assert preview["preview"] == "hello"


def test_get_file_metadata_contract(tmp_path):
    router = OrganizerToolRouter()
    target = tmp_path / "doc.txt"
    target.write_text("hello world")
    with pytest.raises(ValueError, match="path must be non-empty"):
        router.get_file_metadata("")
    md = router.get_file_metadata(str(target))
    assert md["path"] == str(target)
    assert md["size_bytes"] == target.stat().st_size


def test_get_folder_manifest_contract(tmp_path):
    router = OrganizerToolRouter()
    folder = tmp_path / "folder"
    folder.mkdir()
    (folder / "a.txt").write_text("a")
    (folder / "b.txt").write_text("b")
    with pytest.raises(ValueError, match="folder_path must be non-empty"):
        router.get_folder_manifest("")
    manifest = router.get_folder_manifest(str(folder))
    assert {item["name"] for item in manifest} == {"a.txt", "b.txt"}


def test_propose_cleanup_contract():
    router = OrganizerToolRouter()
    with pytest.raises(ValueError, match="hits must be non-empty"):
        router.propose_cleanup([])
    proposals = router.propose_cleanup([{"path": "/tmp/a.txt", "score": 0.9}])
    assert proposals[0]["kind"] == "cleanup"


def test_propose_restructure_contract():
    router = OrganizerToolRouter()
    with pytest.raises(ValueError, match="manifest must be non-empty"):
        router.propose_restructure([])
    proposals = router.propose_restructure([{"path": "/tmp/a.txt", "ext": ".txt"}])
    assert proposals[0]["kind"] == "restructure"


def test_create_action_batch_contract():
    router = OrganizerToolRouter()
    with pytest.raises(ValueError, match="proposals must be non-empty"):
        router.create_action_batch([])
    batch = router.create_action_batch(
        [{"source": "/tmp/a.txt", "destination": "/tmp/b.txt"}]
    )
    assert "batch_id" in batch
    assert batch["count"] == 1


def test_apply_action_batch_contract():
    router = OrganizerToolRouter()
    with pytest.raises(ValueError, match="unknown batch_id"):
        router.apply_action_batch("missing")
    created = router.create_action_batch(
        [{"source": "/tmp/a.txt", "destination": "/tmp/b.txt"}]
    )
    applied = router.apply_action_batch(created["batch_id"])
    assert applied["applied"] is True


def test_undo_action_batch_contract():
    router = OrganizerToolRouter()
    with pytest.raises(ValueError, match="unknown batch_id"):
        router.undo_action_batch("missing")
    created = router.create_action_batch(
        [{"source": "/tmp/a.txt", "destination": "/tmp/b.txt"}]
    )
    router.apply_action_batch(created["batch_id"])
    undone = router.undo_action_batch(created["batch_id"])
    assert undone["undone"] is True

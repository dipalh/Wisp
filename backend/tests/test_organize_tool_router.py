from __future__ import annotations

from pathlib import Path

import pytest

import services.actions as action_store
from services.actions.models import ActionStatus
from services.organizer.tool_router import OrganizerToolRouter
from services.roots import add_root, clear as clear_roots


@pytest.fixture(autouse=True)
def _clean_roots():
    clear_roots()
    yield
    clear_roots()


def test_semantic_search_contract(monkeypatch):
    router = OrganizerToolRouter()
    with pytest.raises(ValueError, match="query must be non-empty"):
        router.semantic_search("", limit=5)
    monkeypatch.setattr(
        "services.organizer.tool_router.pipeline.search",
        lambda query, k: [
            type(
                "Hit",
                (),
                {
                    "file_path": "/tmp/result.txt",
                    "score": 0.95,
                    "text": "invoice details",
                    "file_id": "file-1",
                    "ext": ".txt",
                    "depth": "deep",
                },
            )(),
        ],
    )
    results = router.semantic_search("invoice", limit=2)
    assert isinstance(results, list)
    assert results[0]["path"] == "/tmp/result.txt"
    assert results[0]["snippet"] == "invoice details"


def test_semantic_search_is_filtered_to_active_root(monkeypatch, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    add_root(str(root))
    inside = root / "inside.txt"
    outside = tmp_path / "outside.txt"
    inside.write_text("inside")
    outside.write_text("outside")

    monkeypatch.setattr(
        "services.organizer.tool_router.pipeline.search",
        lambda query, k: [
            type(
                "Hit",
                (),
                {
                    "file_path": str(outside),
                    "score": 0.99,
                    "text": "outside hit",
                    "file_id": "outside-1",
                    "ext": ".txt",
                    "depth": "deep",
                },
            )(),
            type(
                "Hit",
                (),
                {
                    "file_path": str(inside),
                    "score": 0.85,
                    "text": "inside hit",
                    "file_id": "inside-1",
                    "ext": ".txt",
                    "depth": "deep",
                },
            )(),
        ],
    )

    router = OrganizerToolRouter(root_path=str(root))
    results = router.semantic_search("inside", limit=5)

    assert [item["path"] for item in results] == [str(inside)]


def test_get_preview_contract(tmp_path):
    router = OrganizerToolRouter()
    target = tmp_path / "doc.txt"
    target.write_text("hello world")
    with pytest.raises(ValueError, match="path must be non-empty"):
        router.get_preview("")
    preview = router.get_preview(str(target), max_chars=5)
    assert preview["path"] == str(target)
    assert preview["preview"] == "hello"


def test_get_preview_falls_back_to_index_when_file_is_missing(monkeypatch, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    add_root(str(root))
    missing = root / "missing.txt"

    monkeypatch.setattr(
        "services.organizer.tool_router.embedding_store.list_files",
        lambda: [
            {
                "file_id": "file-1",
                "file_path": str(missing),
                "ext": ".txt",
                "text": "[FILE INDEX] Indexed fallback preview text",
                "tags": [],
            }
        ],
    )

    router = OrganizerToolRouter(root_path=str(root))
    preview = router.get_preview(str(missing), max_chars=12)

    assert preview["path"] == str(missing)
    assert preview["preview"] == "Indexed fall"
    assert preview["source"] == "index"


def test_get_file_metadata_contract(tmp_path):
    router = OrganizerToolRouter()
    target = tmp_path / "doc.txt"
    target.write_text("hello world")
    with pytest.raises(ValueError, match="path must be non-empty"):
        router.get_file_metadata("")
    md = router.get_file_metadata(str(target))
    assert md["path"] == str(target)
    assert md["size_bytes"] == target.stat().st_size


def test_get_file_metadata_includes_index_context_for_missing_file(monkeypatch, tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    add_root(str(root))
    missing = root / "ghost.txt"

    monkeypatch.setattr(
        "services.organizer.tool_router.embedding_store.list_files",
        lambda: [
            {
                "file_id": "file-1",
                "file_path": str(missing),
                "ext": ".txt",
                "text": "[FILE INDEX] Ghost document summary",
                "tags": ["project", "stale"],
            }
        ],
    )

    router = OrganizerToolRouter(root_path=str(root))
    md = router.get_file_metadata(str(missing))

    assert md["exists"] is False
    assert md["indexed"] is True
    assert md["tags"] == ["project", "stale"]
    assert "ghost document summary" in md["indexed_preview"].lower()


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


def test_get_folder_manifest_recursive_and_root_scoped(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    add_root(str(root))
    nested = root / "docs" / "q1"
    nested.mkdir(parents=True)
    (root / "top.txt").write_text("top")
    (nested / "report.txt").write_text("report")

    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "escape.txt").write_text("nope")

    router = OrganizerToolRouter(root_path=str(root))
    manifest = router.get_folder_manifest(str(root), recursive=True, max_depth=3)

    paths = {item["path"] for item in manifest}
    assert str(root / "top.txt") in paths
    assert str(nested / "report.txt") in paths
    assert any(item["kind"] == "directory" and item["path"] == str(root / "docs") for item in manifest)

    with pytest.raises(ValueError, match="outside the active organizer root"):
        router.get_folder_manifest(str(outside), recursive=True)


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


def test_create_action_batch_contract(tmp_path):
    action_store.configure_db(tmp_path / "actions.db")
    action_store.clear()
    router = OrganizerToolRouter()
    with pytest.raises(ValueError, match="proposals must be non-empty"):
        router.create_action_batch([])
    source = tmp_path / "a.txt"
    source.write_text("hello")
    destination = tmp_path / "organized" / "a.txt"
    batch = router.create_action_batch(
        [{"source": str(source), "destination": str(destination)}]
    )
    assert "batch_id" in batch
    assert batch["count"] == 1
    durable = action_store.get_batch(batch["batch_id"])
    assert durable is not None
    assert len(durable["action_ids"]) == 1
    recorded = action_store.get(durable["action_ids"][0])
    assert recorded is not None
    assert recorded.status == ActionStatus.ACCEPTED


def test_apply_action_batch_contract(tmp_path):
    action_store.configure_db(tmp_path / "actions.db")
    action_store.clear()
    router = OrganizerToolRouter()
    with pytest.raises(ValueError, match="unknown batch_id"):
        router.apply_action_batch("missing")
    source = tmp_path / "a.txt"
    source.write_text("hello")
    destination = tmp_path / "organized" / "a.txt"
    created = router.create_action_batch(
        [{"source": str(source), "destination": str(destination)}]
    )
    applied = router.apply_action_batch(created["batch_id"])
    assert applied["applied"] == 1
    assert applied["failed"] == 0
    assert applied["status"] == "APPLIED"
    assert not source.exists()
    assert destination.exists()


def test_undo_action_batch_contract(tmp_path):
    action_store.configure_db(tmp_path / "actions.db")
    action_store.clear()
    router = OrganizerToolRouter()
    with pytest.raises(ValueError, match="unknown batch_id"):
        router.undo_action_batch("missing")
    source = tmp_path / "a.txt"
    source.write_text("hello")
    destination = tmp_path / "organized" / "a.txt"
    created = router.create_action_batch(
        [{"source": str(source), "destination": str(destination)}]
    )
    router.apply_action_batch(created["batch_id"])
    undone = router.undo_action_batch(created["batch_id"])
    assert undone["undone"] == 1
    assert undone["failed"] == 0
    assert undone["status"] == "UNDONE"
    assert source.exists()
    assert not destination.exists()

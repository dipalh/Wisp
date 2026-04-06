from __future__ import annotations

from pathlib import Path

import services.actions as action_store
from services.actions.batch_executor import apply_batch as apply_action_batch
from services.actions.batch_executor import undo_batch as undo_action_batch
from services.actions.models import Action, ActionStatus, ActionType
from services.embedding import pipeline


class OrganizerToolRouter:
    def __init__(self) -> None:
        pass

    def semantic_search(self, query: str, *, limit: int = 5) -> list[dict]:
        if not query.strip():
            raise ValueError("query must be non-empty")
        if limit <= 0:
            raise ValueError("limit must be positive")
        hits = pipeline.search(query, k=limit)
        return [
            {
                "path": hit.file_path,
                "score": hit.score,
                "snippet": hit.text[:200],
                "file_id": hit.file_id,
                "ext": hit.ext,
                "depth": hit.depth,
            }
            for hit in hits[:limit]
        ]

    def get_preview(self, path: str, *, max_chars: int = 200) -> dict:
        if not path.strip():
            raise ValueError("path must be non-empty")
        p = Path(path)
        text = p.read_text(errors="replace") if p.exists() and p.is_file() else ""
        return {"path": str(p), "preview": text[:max_chars]}

    def get_file_metadata(self, path: str) -> dict:
        if not path.strip():
            raise ValueError("path must be non-empty")
        p = Path(path)
        if not p.exists():
            return {"path": str(p), "exists": False, "size_bytes": 0}
        st = p.stat()
        return {"path": str(p), "exists": True, "size_bytes": st.st_size, "ext": p.suffix.lower()}

    def get_folder_manifest(self, folder_path: str) -> list[dict]:
        if not folder_path.strip():
            raise ValueError("folder_path must be non-empty")
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            return []
        rows: list[dict] = []
        for child in sorted(folder.iterdir(), key=lambda c: c.name.lower()):
            if child.is_file():
                rows.append({"name": child.name, "path": str(child), "ext": child.suffix.lower()})
        return rows

    def propose_cleanup(self, hits: list[dict]) -> list[dict]:
        if not hits:
            raise ValueError("hits must be non-empty")
        first = hits[0]
        return [
            {
                "kind": "cleanup",
                "targets": [first.get("path", "")],
                "reasons": ["high junk score"],
                "citations": [first.get("path", "")],
            }
        ]

    def propose_restructure(self, manifest: list[dict]) -> list[dict]:
        if not manifest:
            raise ValueError("manifest must be non-empty")
        first = manifest[0]
        src = first.get("path", "")
        name = Path(src).name if src else "file"
        return [
            {
                "kind": "restructure",
                "targets": [src],
                "destination": f"Documents/{name}",
                "reasons": ["group by type"],
                "citations": [src],
            }
        ]

    def create_action_batch(self, proposals: list[dict]) -> dict:
        if not proposals:
            raise ValueError("proposals must be non-empty")
        action_ids: list[str] = []
        for proposal in proposals:
            src = proposal.get("source") or (proposal.get("targets") or [""])[0]
            dst = proposal.get("destination") or proposal.get("suggested_path") or ""
            if not src or not dst:
                continue
            action = Action(
                type=ActionType.MOVE,
                label=f"Organize {src} -> {dst}",
                targets=[src],
                before_state={"path": src},
                after_state={"path": dst},
                status=ActionStatus.ACCEPTED,
                actor="organizer",
                source="tool_router",
            )
            action_store.add(action)
            action_ids.append(action.id)
        if not action_ids:
            raise ValueError("proposals must contain actionable source/destination paths")
        batch = action_store.create_batch(action_ids, actor="organizer")
        for action_id in action_ids:
            action = action_store.get(action_id)
            if action is None:
                continue
            action.batch_id = batch["batch_id"]
            action_store.add(action)
        return {"batch_id": batch["batch_id"], "count": len(action_ids)}

    def apply_action_batch(self, batch_id: str) -> dict:
        result = apply_action_batch(batch_id)
        if result is None:
            raise ValueError("unknown batch_id")
        return {"batch_id": batch_id, "applied": True}

    def undo_action_batch(self, batch_id: str) -> dict:
        result = undo_action_batch(batch_id)
        if result is None:
            raise ValueError("unknown batch_id")
        return {"batch_id": batch_id, "undone": True}

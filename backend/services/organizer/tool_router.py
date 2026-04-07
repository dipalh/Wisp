from __future__ import annotations

from pathlib import Path

import services.actions as action_store
from services.actions.batch_executor import apply_batch as apply_action_batch
from services.actions.batch_executor import undo_batch as undo_action_batch
from services.actions.models import Action, ActionStatus, ActionType
from services.embedding import store as embedding_store
from services.embedding import pipeline
from services.roots import is_under_root


class OrganizerToolRouter:
    def __init__(self, *, root_path: str | None = None) -> None:
        self.root_path = str(Path(root_path).resolve()) if root_path else None

    def _ensure_path_allowed(self, target_path: str, *, label: str) -> Path:
        candidate = Path(target_path).resolve()
        if self.root_path is not None and not candidate.is_relative_to(Path(self.root_path)):
            raise ValueError(f"{label} is outside the active organizer root: {candidate}")
        if self.root_path is None and not is_under_root(candidate):
            raise ValueError(f"{label} is outside registered roots: {candidate}")
        return candidate

    def _indexed_record_for(self, target_path: str) -> dict | None:
        for record in embedding_store.list_files():
            if record.get("file_path") == target_path:
                return record
        return None

    def semantic_search(self, query: str, *, limit: int = 5) -> list[dict]:
        if not query.strip():
            raise ValueError("query must be non-empty")
        if limit <= 0:
            raise ValueError("limit must be positive")
        hits = pipeline.search(query, k=limit)
        rows = [
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
        if self.root_path is None:
            return rows
        root = Path(self.root_path)
        return [row for row in rows if Path(row["path"]).resolve().is_relative_to(root)]

    def get_preview(self, path: str, *, max_chars: int = 200) -> dict:
        if not path.strip():
            raise ValueError("path must be non-empty")
        p = self._ensure_path_allowed(path, label="path")
        if p.exists() and p.is_file():
            text = p.read_text(errors="replace")
            return {"path": str(p), "preview": text[:max_chars], "source": "filesystem"}
        indexed = self._indexed_record_for(str(p))
        if indexed is not None:
            text = (indexed.get("text") or "").replace("[FILE INDEX] ", "")
            return {"path": str(p), "preview": text[:max_chars], "source": "index"}
        return {"path": str(p), "preview": "", "source": "missing"}

    def get_file_metadata(self, path: str) -> dict:
        if not path.strip():
            raise ValueError("path must be non-empty")
        p = self._ensure_path_allowed(path, label="path")
        indexed = self._indexed_record_for(str(p))
        if not p.exists():
            return {
                "path": str(p),
                "exists": False,
                "size_bytes": 0,
                "ext": p.suffix.lower(),
                "name": p.name,
                "parent_dir": str(p.parent),
                "indexed": indexed is not None,
                "tags": list(indexed.get("tags", [])) if indexed is not None else [],
                "indexed_preview": (indexed.get("text", "").replace("[FILE INDEX] ", "")[:200] if indexed else ""),
            }
        st = p.stat()
        return {
            "path": str(p),
            "exists": True,
            "size_bytes": st.st_size,
            "ext": p.suffix.lower(),
            "name": p.name,
            "parent_dir": str(p.parent),
            "indexed": indexed is not None,
            "tags": list(indexed.get("tags", [])) if indexed is not None else [],
            "indexed_preview": (indexed.get("text", "").replace("[FILE INDEX] ", "")[:200] if indexed else ""),
        }

    def get_folder_manifest(
        self,
        folder_path: str,
        *,
        recursive: bool = False,
        max_depth: int = 2,
        max_entries: int = 200,
    ) -> list[dict]:
        if not folder_path.strip():
            raise ValueError("folder_path must be non-empty")
        folder = self._ensure_path_allowed(folder_path, label="folder_path")
        if not folder.exists() or not folder.is_dir():
            return []
        if not recursive:
            rows: list[dict] = []
            for child in sorted(folder.iterdir(), key=lambda c: c.name.lower()):
                if child.is_file():
                    rows.append({"kind": "file", "name": child.name, "path": str(child), "ext": child.suffix.lower(), "depth": 1})
            return rows

        rows: list[dict] = []

        def _walk(current: Path, depth: int) -> None:
            if depth > max_depth or len(rows) >= max_entries:
                return
            for child in sorted(current.iterdir(), key=lambda c: (c.is_file(), c.name.lower())):
                if len(rows) >= max_entries:
                    return
                if child.is_dir():
                    rows.append({"kind": "directory", "name": child.name, "path": str(child), "depth": depth})
                    _walk(child, depth + 1)
                elif child.is_file():
                    rows.append({"kind": "file", "name": child.name, "path": str(child), "ext": child.suffix.lower(), "depth": depth})

        _walk(folder, 1)
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
        return result

    def undo_action_batch(self, batch_id: str) -> dict:
        result = undo_action_batch(batch_id)
        if result is None:
            raise ValueError("unknown batch_id")
        return result

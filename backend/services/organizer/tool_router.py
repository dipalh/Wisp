from __future__ import annotations

import uuid
from pathlib import Path


class OrganizerToolRouter:
    def __init__(self) -> None:
        self._batches: dict[str, dict] = {}

    def semantic_search(self, query: str, *, limit: int = 5) -> list[dict]:
        if not query.strip():
            raise ValueError("query must be non-empty")
        if limit <= 0:
            raise ValueError("limit must be positive")
        return [
            {
                "path": "/mock/result.txt",
                "score": 0.95,
                "snippet": f"match for {query}",
            }
        ][:limit]

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
        batch_id = uuid.uuid4().hex[:12]
        self._batches[batch_id] = {"proposals": proposals, "applied": False}
        return {"batch_id": batch_id, "count": len(proposals)}

    def apply_action_batch(self, batch_id: str) -> dict:
        batch = self._batches.get(batch_id)
        if batch is None:
            raise ValueError("unknown batch_id")
        batch["applied"] = True
        return {"batch_id": batch_id, "applied": True}

    def undo_action_batch(self, batch_id: str) -> dict:
        batch = self._batches.get(batch_id)
        if batch is None:
            raise ValueError("unknown batch_id")
        if not batch.get("applied", False):
            return {"batch_id": batch_id, "undone": True}
        batch["applied"] = False
        return {"batch_id": batch_id, "undone": True}

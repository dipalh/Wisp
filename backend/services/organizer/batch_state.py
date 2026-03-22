from __future__ import annotations

import threading
import uuid
from pathlib import Path
import shutil

_lock = threading.Lock()
_batches: dict[str, dict] = {}


def create_batch(proposal_id: str, mappings: list[dict[str, str]]) -> str:
    batch_id = uuid.uuid4().hex[:12]
    with _lock:
        _batches[batch_id] = {
            "proposal_id": proposal_id,
            "mappings": list(mappings),
            "applied": False,
        }
    return batch_id


def has_batch(batch_id: str) -> bool:
    with _lock:
        return batch_id in _batches


def apply_batch(batch_id: str) -> None:
    with _lock:
        batch = _batches.get(batch_id)
        if batch is None:
            raise KeyError(batch_id)
        mappings = list(batch.get("mappings", []))
    for m in mappings:
        src_path = m.get("original_path", "")
        dst_path = m.get("suggested_path", "")
        if not src_path or not dst_path:
            continue
        src = Path(src_path)
        dst = Path(dst_path)
        if dst.exists():
            raise FileExistsError(dst_path)
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    with _lock:
        _batches[batch_id]["applied"] = True


def undo_batch(batch_id: str) -> None:
    with _lock:
        batch = _batches.get(batch_id)
        if batch is None:
            raise KeyError(batch_id)
        mappings = list(batch.get("mappings", []))
    for m in mappings:
        src_path = m.get("suggested_path", "")
        dst_path = m.get("original_path", "")
        if not src_path or not dst_path:
            continue
        src = Path(src_path)
        dst = Path(dst_path)
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    with _lock:
        _batches[batch_id]["applied"] = False


def clear() -> None:
    with _lock:
        _batches.clear()

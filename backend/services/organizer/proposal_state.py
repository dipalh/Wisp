from __future__ import annotations

import threading

_lock = threading.Lock()
_accepted_proposals: set[str] = set()
_proposal_mappings: dict[str, list[dict[str, str]]] = {}
_proposal_batches: dict[str, str] = {}


def accept(
    proposal_id: str,
    mappings: list[dict[str, str]] | None = None,
    *,
    batch_id: str | None = None,
) -> None:
    with _lock:
        _accepted_proposals.add(proposal_id)
        _proposal_mappings[proposal_id] = mappings or []
        if batch_id is not None:
            _proposal_batches[proposal_id] = batch_id


def is_accepted(proposal_id: str) -> bool:
    with _lock:
        return proposal_id in _accepted_proposals


def mappings_for(proposal_id: str) -> list[dict[str, str]]:
    with _lock:
        return list(_proposal_mappings.get(proposal_id, []))


def batch_for(proposal_id: str) -> str | None:
    with _lock:
        return _proposal_batches.get(proposal_id)


def clear() -> None:
    with _lock:
        _accepted_proposals.clear()
        _proposal_mappings.clear()
        _proposal_batches.clear()

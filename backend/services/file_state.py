from __future__ import annotations

from enum import Enum


class FileState(str, Enum):
    DISCOVERED = "DISCOVERED"
    INDEXED = "INDEXED"
    STALE = "STALE"
    MISSING_EXTERNALLY = "MISSING_EXTERNALLY"
    MOVED_EXTERNALLY = "MOVED_EXTERNALLY"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    LOCKED = "LOCKED"
    QUARANTINED = "QUARANTINED"


_STATE_DEFAULT_MESSAGES: dict[str, str] = {
    FileState.MISSING_EXTERNALLY.value: "File is missing on disk at the previously indexed path.",
    FileState.MOVED_EXTERNALLY.value: "File path changed outside Wisp and needs reconciliation.",
    FileState.STALE.value: "File exists on disk but was not indexed in the most recent scan.",
    FileState.PERMISSION_DENIED.value: "Access to the file or directory was denied.",
    FileState.LOCKED.value: "File or directory is locked by another process.",
    FileState.QUARANTINED.value: "File is in quarantine and excluded from active indexing.",
}


def normalize_error_code(file_state: str, error_code: str) -> str:
    if error_code:
        return error_code
    if file_state and file_state != FileState.INDEXED.value:
        return file_state
    return ""


def normalize_error_message(file_state: str, error_message: str) -> str:
    if error_message:
        return error_message
    base = _STATE_DEFAULT_MESSAGES.get(file_state, "")
    if not base:
        return ""
    if file_state and file_state != FileState.INDEXED.value:
        return f"{file_state}: {base}"
    return base

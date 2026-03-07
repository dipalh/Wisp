from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Callable


class ScanStage(str, Enum):
    DISCOVERED = "DISCOVERED"
    PREVIEWED = "PREVIEWED"
    EMBEDDED = "EMBEDDED"
    SCORED = "SCORED"


_STAGE_ORDER = {
    ScanStage.DISCOVERED: 1,
    ScanStage.PREVIEWED: 2,
    ScanStage.EMBEDDED: 3,
    ScanStage.SCORED: 4,
}


@dataclass
class ScanStats:
    discovered: int = 0
    previewed: int = 0
    embedded: int = 0
    scored: int = 0
    cached: int = 0
    failed: int = 0

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class ScanProgressTracker:
    def __init__(self, job_id: str, emit_progress: Callable[..., None]) -> None:
        self.job_id = job_id
        self._emit_progress = emit_progress
        self.stats = ScanStats()
        self.total = 0
        self.completed = 0
        self.stage = ScanStage.DISCOVERED

    def begin(self, total: int) -> None:
        self.total = total
        self.stats.discovered = total
        self._emit(0, total, f"Discovered {total} files", ScanStage.DISCOVERED)

    def record_result(self, file_path: Path, *, depth: str, skipped: bool) -> None:
        self.stats.previewed += 1
        self._emit(self.completed, self.total, f"Previewed {file_path.name}", ScanStage.PREVIEWED)
        if depth == "deep":
            self.stats.embedded += 1
            self._emit(self.completed, self.total, f"Embedded {file_path.name}", ScanStage.EMBEDDED)
        if skipped:
            self.stats.cached += 1
        self.stats.scored += 1
        self.completed += 1
        self._emit(self.completed, self.total, f"Scored {self.completed}/{self.total}: {file_path.name}", ScanStage.SCORED)

    def record_failure(self, file_path: Path, message: str) -> None:
        self.stats.failed += 1
        self.completed += 1
        self._emit(self.completed, self.total, f"Failed {file_path.name}: {message}", ScanStage.SCORED)

    def record_issue(self, issue_path: Path, message: str) -> None:
        self.stats.failed += 1
        self.completed += 1
        self._emit(self.completed, self.total, f"Issue {issue_path.name}: {message}", ScanStage.SCORED)

    def _emit(self, current: int, total: int, message: str, candidate_stage: ScanStage) -> None:
        if _STAGE_ORDER[candidate_stage] > _STAGE_ORDER[self.stage]:
            self.stage = candidate_stage
        self._emit_progress(
            self.job_id,
            current,
            total,
            message,
            stage=self.stage.value,
            stats=self.stats.to_dict(),
        )

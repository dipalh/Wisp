"""
Pydantic models for the Action Engine.

An Action represents any file operation (proposed or applied) with enough
state to support undo. The lifecycle is:

  PROPOSED → APPLIED → UNDONE

- PROPOSED: the action has been suggested but not yet executed.
- APPLIED:  the action has been executed (file moved, deleted, etc.).
- UNDONE:   the action was reversed (file moved back, etc.).
"""
from __future__ import annotations

import time
import uuid
from enum import Enum

from pydantic import BaseModel, Field


class ActionType(str, Enum):
    MOVE   = "MOVE"
    DELETE = "DELETE"
    RENAME = "RENAME"
    TAG    = "TAG"


class ActionStatus(str, Enum):
    PROPOSED = "PROPOSED"
    APPLIED  = "APPLIED"
    UNDONE   = "UNDONE"


class Action(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:12])
    type: ActionType
    label: str = Field(description="Human-readable description, e.g. \"Move resume.pdf → Documents/\"")
    targets: list[str] = Field(description="File paths affected by this action")
    before_state: dict = Field(description="State before the action: {path: original_path, ...}")
    after_state: dict = Field(description="State after the action: {path: new_path} for MOVE; {} for DELETE")
    timestamp: float = Field(default_factory=time.time)
    status: ActionStatus = ActionStatus.PROPOSED

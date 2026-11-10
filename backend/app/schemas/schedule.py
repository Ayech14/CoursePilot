"""Schedule, proposal and session contracts."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, ValidationInfo, field_validator

from app.models.enums import (
    ChangeAction,
    ProposalStatus,
    ProposalTrigger,
    SessionOrigin,
    SessionStatus,
)


class AtRiskRead(BaseModel):
    task_id: uuid.UUID
    task_title: str
    deadline_at: datetime | None
    shortfall_minutes: int
    reason: str
    message: str


class UnplacedRead(BaseModel):
    task_id: uuid.UUID
    task_title: str
    minutes: int


class ProposalChangeRead(BaseModel):
    id: uuid.UUID
    action: ChangeAction
    session_id: uuid.UUID | None
    task_id: uuid.UUID
    task_title: str
    course_name: str | None
    course_color: str | None
    before_start_at: datetime | None
    before_end_at: datetime | None
    after_start_at: datetime | None
    after_end_at: datetime | None
    explanation: str | None
    sticky_released: bool


class ProposalRead(BaseModel):
    id: uuid.UUID
    trigger: ProposalTrigger
    status: ProposalStatus
    created_at: datetime
    unchanged_sessions: int
    stability_percent: int
    at_risk: list[AtRiskRead]
    unplaced: list[UnplacedRead]
    changes: list[ProposalChangeRead]


class PreviewRequest(BaseModel):
    # Repair changes as little as possible. Regenerate replaces every unprotected session.
    mode: Literal["repair", "regenerate"] = "repair"


class ApplyRequest(BaseModel):
    rejected_change_ids: Annotated[list[uuid.UUID], Field(max_length=2000)] = []


class ApplyResult(BaseModel):
    created: int
    moved: int
    resized: int
    removed: int
    skipped: int


class ScheduleStatus(BaseModel):
    needs_update: bool
    added: int
    moved: int
    resized: int
    removed: int
    missed_sessions: int
    at_risk: int


class SessionRead(BaseModel):
    id: uuid.UUID
    task_id: uuid.UUID
    task_title: str
    course_name: str | None
    course_color: str | None
    start_at: datetime
    end_at: datetime
    status: SessionStatus
    origin: SessionOrigin
    is_locked: bool
    is_user_modified: bool
    explanation: str | None
    actual_minutes: int


_MIN_SESSION_MINUTES = 5
_MAX_SESSION_MINUTES = 480


class _SessionTimes(BaseModel):
    start_at: AwareDatetime
    end_at: AwareDatetime

    @field_validator("end_at")
    @classmethod
    def sensible_length(cls, value: datetime, info: ValidationInfo) -> datetime:
        start = info.data.get("start_at")
        if start is None:
            return value
        minutes = (value - start).total_seconds() / 60
        if minutes < _MIN_SESSION_MINUTES:
            raise ValueError(f"must be at least {_MIN_SESSION_MINUTES} minutes after the start")
        if minutes > _MAX_SESSION_MINUTES:
            raise ValueError("a session cannot be longer than 8 hours")
        return value


class SessionCreate(_SessionTimes):
    task_id: uuid.UUID
    acknowledge_warnings: bool = False


class SessionUpdate(_SessionTimes):
    acknowledge_warnings: bool = False


class PlacementQuery(_SessionTimes):
    """Check a time without saving. Give `session_id` when moving an existing session."""

    task_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None


class ConflictRead(BaseModel):
    kind: str
    message: str
    session_id: uuid.UUID | None


class WarningRead(BaseModel):
    kind: str
    message: str


class SlotRead(BaseModel):
    start_at: datetime
    end_at: datetime


class PlacementRead(BaseModel):
    ok: bool
    conflicts: list[ConflictRead]
    warnings: list[WarningRead]
    alternatives: list[SlotRead]


class ActiveTimerRead(BaseModel):
    session: SessionRead
    running: bool
    elapsed_seconds: int


class TimerFinish(BaseModel):
    """How a timed session ended. Everything is optional; the timer's own total is the default."""

    # Lowers the timed total, for a timer that was left running by accident.
    actual_minutes: Annotated[int, Field(ge=0, le=100_000)] | None = None
    remaining_minutes: Annotated[int, Field(ge=0, le=30_000)] | None = None
    mark_task_completed: bool = False

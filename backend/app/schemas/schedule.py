"""Schedule, proposal and session contracts."""

import uuid
from datetime import datetime

from pydantic import BaseModel

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


class ProposalRead(BaseModel):
    id: uuid.UUID
    trigger: ProposalTrigger
    status: ProposalStatus
    created_at: datetime
    unchanged_sessions: int
    at_risk: list[AtRiskRead]
    unplaced: list[UnplacedRead]
    changes: list[ProposalChangeRead]


class ApplyResult(BaseModel):
    created: int
    removed: int


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
    explanation: str | None

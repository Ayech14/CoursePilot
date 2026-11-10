"""Task contracts."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.models.enums import TaskStatus, TaskType
from app.schemas.common import LongText, reject_null

TaskTitle = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
# Capped at 500 hours: enough for any real task, and it catches unit mistakes.
EffortMinutes = Annotated[int, Field(gt=0, le=30_000)]
RemainingMinutes = Annotated[int, Field(ge=0, le=30_000)]
PriorityLevel = Annotated[int, Field(ge=1, le=4)]


class TaskCreate(BaseModel):
    title: TaskTitle
    description: LongText | None = None
    course_id: uuid.UUID | None = None
    task_type: TaskType
    deadline_at: AwareDatetime | None = None
    estimated_minutes: EffortMinutes
    # Defaults to the estimate. A new task always has work left, so zero is not allowed.
    remaining_minutes: EffortMinutes | None = None
    priority: PriorityLevel = 2


class TaskUpdate(BaseModel):
    title: TaskTitle | None = None
    description: LongText | None = None
    course_id: uuid.UUID | None = None
    task_type: TaskType | None = None
    deadline_at: AwareDatetime | None = None
    estimated_minutes: EffortMinutes | None = None
    remaining_minutes: RemainingMinutes | None = None
    priority: PriorityLevel | None = None
    status: TaskStatus | None = None

    _required = field_validator(
        "title",
        "task_type",
        "estimated_minutes",
        "remaining_minutes",
        "priority",
        "status",
        mode="before",
    )(reject_null)


class TaskProgress(BaseModel):
    minutes_spent: Annotated[int, Field(gt=0, le=1440)] | None = None
    remaining_minutes: RemainingMinutes | None = None
    mark_completed: bool = False


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    course_id: uuid.UUID | None
    title: str
    description: str | None
    task_type: TaskType
    deadline_at: datetime | None
    estimated_minutes: int
    remaining_minutes: int
    actual_minutes: int
    priority: int
    status: TaskStatus
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

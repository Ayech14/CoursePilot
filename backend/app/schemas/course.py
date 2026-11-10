"""Course contracts."""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, field_validator

from app.schemas.common import LongText, ShortText, reject_null
from app.schemas.task import TaskRead

HexColor = Annotated[str, StringConstraints(pattern=r"^#[0-9a-fA-F]{6}$", to_lower=True)]
CourseCode = Annotated[str, StringConstraints(strip_whitespace=True, max_length=32)]


class CourseCreate(BaseModel):
    name: ShortText
    code: CourseCode | None = None
    description: LongText | None = None
    color: HexColor


class CourseUpdate(BaseModel):
    name: ShortText | None = None
    code: CourseCode | None = None
    description: LongText | None = None
    color: HexColor | None = None
    archived: bool | None = None

    _required = field_validator("name", "color", "archived", mode="before")(reject_null)


class CourseProgress(BaseModel):
    total_tasks: int = 0
    completed_tasks: int = 0
    estimated_minutes: int = 0
    remaining_minutes: int = 0
    actual_minutes: int = 0
    next_deadline_at: datetime | None = None


class CourseRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    code: str | None
    description: str | None
    color: str
    archived_at: datetime | None
    created_at: datetime
    progress: CourseProgress = CourseProgress()


class CourseDetail(CourseRead):
    upcoming_tasks: list[TaskRead]

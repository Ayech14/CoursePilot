"""Connected calendar and deadline suggestion contracts."""

import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.models.enums import BlockCategory, TaskType
from app.schemas.common import ShortText
from app.schemas.task import EffortMinutes

FeedUrl = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]


class FeedCreate(BaseModel):
    name: ShortText
    url: FeedUrl


class FeedUpdate(BaseModel):
    name: ShortText


class FeedRead(BaseModel):
    id: uuid.UUID
    name: str
    # Feed links often contain a private token, so only the website is shown back.
    url_hint: str
    last_synced_at: datetime | None
    last_error: str | None
    busy_count: int
    pending_deadlines: int


class SuggestionRead(BaseModel):
    id: uuid.UUID
    title: str
    due_at: datetime
    feed_name: str
    course_id: uuid.UUID | None
    course_name: str | None


class SuggestionAccept(BaseModel):
    estimated_minutes: EffortMinutes
    task_type: TaskType = TaskType.ASSIGNMENT
    course_id: uuid.UUID | None = None
    priority: Annotated[int, Field(ge=1, le=4)] = 2
    title: ShortText | None = None


class BusyRead(BaseModel):
    """One occurrence of busy time, whatever its source, for drawing on the calendar."""

    source: Literal["weekly", "once", "calendar"]
    id: uuid.UUID
    title: str
    category: BlockCategory
    start_at: datetime
    end_at: datetime
    feed_name: str | None

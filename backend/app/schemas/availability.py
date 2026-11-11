"""Availability and study preference contracts.

Weekly values are local wall-clock minutes; one-off blocks are instants. See ARCHITECTURE.md
section 4 for why they differ.
"""

import uuid
from datetime import datetime
from typing import Annotated

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
)

from app.models.enums import BlockCategory
from app.schemas.common import ShortText

DayOfWeek = Annotated[int, Field(ge=0, le=6)]
StartMinute = Annotated[int, Field(ge=0, lt=1440)]
EndMinute = Annotated[int, Field(gt=0, le=1440)]


class WeeklyTime(BaseModel):
    day_of_week: DayOfWeek
    start_minute: StartMinute
    end_minute: EndMinute

    @field_validator("end_minute")
    @classmethod
    def end_after_start(cls, value: int, info: ValidationInfo) -> int:
        start = info.data.get("start_minute")
        if start is not None and value <= start:
            raise ValueError("must be after the start time")
        return value


class WindowsReplace(BaseModel):
    windows: Annotated[list[WeeklyTime], Field(max_length=70)]


class WindowRead(WeeklyTime):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


class RecurringBlockWrite(WeeklyTime):
    title: ShortText
    category: BlockCategory = BlockCategory.OTHER


class RecurringBlockRead(RecurringBlockWrite):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID


class OneOffBlockWrite(BaseModel):
    title: ShortText
    category: BlockCategory = BlockCategory.OTHER
    start_at: AwareDatetime
    end_at: AwareDatetime

    @field_validator("end_at")
    @classmethod
    def end_after_start(cls, value: datetime, info: ValidationInfo) -> datetime:
        start = info.data.get("start_at")
        if start is not None and value <= start:
            raise ValueError("must be after the start time")
        return value


class OneOffBlockRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    category: BlockCategory
    start_at: datetime
    end_at: datetime


class PreferencesWrite(BaseModel):
    preferred_session_minutes: Annotated[int, Field(ge=15, le=240)]
    min_session_minutes: Annotated[int, Field(ge=5, le=240)]
    break_minutes: Annotated[int, Field(ge=0, le=120)]
    max_daily_minutes: Annotated[int, Field(ge=30, le=1440)]
    deadline_buffer_hours: Annotated[int, Field(ge=0, le=168)]
    planning_horizon_days: Annotated[int, Field(ge=1, le=180)]

    @field_validator("min_session_minutes")
    @classmethod
    def minimum_within_preferred(cls, value: int, info: ValidationInfo) -> int:
        preferred = info.data.get("preferred_session_minutes")
        if preferred is not None and value > preferred:
            raise ValueError("cannot be longer than the preferred session")
        return value

    @field_validator("max_daily_minutes")
    @classmethod
    def daily_fits_one_session(cls, value: int, info: ValidationInfo) -> int:
        minimum = info.data.get("min_session_minutes")
        if minimum is not None and value < minimum:
            raise ValueError("must allow at least one minimum-length session")
        return value


class PreferencesRead(PreferencesWrite):
    model_config = ConfigDict(from_attributes=True)

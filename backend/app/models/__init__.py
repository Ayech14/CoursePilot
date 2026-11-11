"""Importing this package registers every table on ``Base.metadata``."""

from app.models.academic import Course, Task
from app.models.availability import (
    AvailabilityWindow,
    OneOffBlock,
    RecurringBlock,
    StudyPreferences,
)
from app.models.calendar import CalendarFeed, DeadlineSuggestion
from app.models.identity import RefreshToken, User
from app.models.notification import Notification
from app.models.schedule import ProposalChange, ScheduleProposal, StudySession, WorkInterval

__all__ = [
    "AvailabilityWindow",
    "CalendarFeed",
    "Course",
    "DeadlineSuggestion",
    "Notification",
    "OneOffBlock",
    "ProposalChange",
    "RecurringBlock",
    "RefreshToken",
    "ScheduleProposal",
    "StudyPreferences",
    "StudySession",
    "Task",
    "User",
    "WorkInterval",
]

"""When a student can study.

Recurring rules are local wall-clock values and one-off blocks are instants, which is why they
are modeled differently. See ARCHITECTURE.md section 4.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, ForeignKey, Index, SmallInteger, String, column, func, text
from sqlalchemy.dialects.postgresql import ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, str_enum
from app.models.enums import BlockCategory


class StudyPreferences(Timestamps, Base):
    __tablename__ = "study_preferences"
    __table_args__ = (
        CheckConstraint("preferred_session_minutes BETWEEN 15 AND 240", name="preferred_range"),
        CheckConstraint(
            "min_session_minutes BETWEEN 5 AND preferred_session_minutes", name="minimum_range"
        ),
        CheckConstraint("break_minutes BETWEEN 0 AND 120", name="break_range"),
        CheckConstraint("max_daily_minutes BETWEEN 30 AND 1440", name="daily_range"),
        CheckConstraint("deadline_buffer_hours BETWEEN 0 AND 168", name="buffer_range"),
        CheckConstraint("planning_horizon_days BETWEEN 1 AND 180", name="horizon_range"),
        CheckConstraint(
            "daily_goal_minutes IS NULL OR daily_goal_minutes BETWEEN 15 AND 720", name="goal_range"
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    preferred_session_minutes: Mapped[int] = mapped_column(default=50, server_default=text("50"))
    min_session_minutes: Mapped[int] = mapped_column(default=25, server_default=text("25"))
    break_minutes: Mapped[int] = mapped_column(default=10, server_default=text("10"))
    max_daily_minutes: Mapped[int] = mapped_column(default=360, server_default=text("360"))
    deadline_buffer_hours: Mapped[int] = mapped_column(default=12, server_default=text("12"))
    planning_horizon_days: Mapped[int] = mapped_column(default=28, server_default=text("28"))
    # The student's own target for the dashboard. It never changes what the scheduler plans.
    daily_goal_minutes: Mapped[int | None]


def _weekly_shape_checks() -> tuple[CheckConstraint, CheckConstraint]:
    return (
        CheckConstraint("day_of_week BETWEEN 0 AND 6", name="day_range"),
        CheckConstraint(
            "start_minute >= 0 AND start_minute < end_minute AND end_minute <= 1440",
            name="minute_range",
        ),
    )


class AvailabilityWindow(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "availability_windows"
    __table_args__ = (
        *_weekly_shape_checks(),
        ExcludeConstraint(
            ("user_id", "="),
            ("day_of_week", "="),
            (func.int4range(column("start_minute"), column("end_minute")), "&&"),
            name="excl_availability_windows_no_overlap",
            using="gist",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    day_of_week: Mapped[int] = mapped_column(SmallInteger)  # 0 = Monday.
    start_minute: Mapped[int] = mapped_column(SmallInteger)  # Minutes since local midnight.
    end_minute: Mapped[int] = mapped_column(SmallInteger)  # Up to 1440, meaning end of day.


class RecurringBlock(UUIDPrimaryKey, Timestamps, Base):
    """A weekly commitment such as a lecture or a job."""

    __tablename__ = "recurring_blocks"
    __table_args__ = (*_weekly_shape_checks(), Index(None, "user_id"))

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120))
    category: Mapped[BlockCategory] = mapped_column(
        str_enum(BlockCategory, "block_category"),
        default=BlockCategory.OTHER,
        server_default="other",
    )
    day_of_week: Mapped[int] = mapped_column(SmallInteger)
    start_minute: Mapped[int] = mapped_column(SmallInteger)
    end_minute: Mapped[int] = mapped_column(SmallInteger)


class OneOffBlock(UUIDPrimaryKey, Timestamps, Base):
    """A single period of unavailability, such as a shift, a night out or a trip.

    Rows with a `feed_id` were imported from a connected calendar. Each sync replaces them, so the
    student edits them at their source, not here.
    """

    __tablename__ = "one_off_blocks"
    __table_args__ = (
        CheckConstraint("start_at < end_at", name="ordered"),
        CheckConstraint(
            "(feed_id IS NULL) = (external_uid IS NULL)", name="import_fields_together"
        ),
        Index(None, "user_id", "start_at"),
        Index(None, "feed_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    title: Mapped[str] = mapped_column(String(120))
    category: Mapped[BlockCategory] = mapped_column(
        str_enum(BlockCategory, "block_category"),
        default=BlockCategory.OTHER,
        server_default="other",
    )
    feed_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("calendar_feeds.id", ondelete="CASCADE")
    )
    external_uid: Mapped[str | None] = mapped_column(String(500))
    start_at: Mapped[datetime]
    end_at: Mapped[datetime]

"""Calendars the student connected by link, and the deadlines found in them."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, str_enum
from app.models.enums import SuggestionStatus


class CalendarFeed(UUIDPrimaryKey, Timestamps, Base):
    """An iCalendar link. Its timed events become busy time; its deadlines become suggestions.

    The link usually contains a private token, so it is stored encrypted (see
    app/core/link_cipher.py) and the API never returns it. Only its host is kept readable, to show.
    """

    __tablename__ = "calendar_feeds"
    __table_args__ = (UniqueConstraint("user_id", "url_digest"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    url_ciphertext: Mapped[str] = mapped_column(Text)
    url_digest: Mapped[str] = mapped_column(String(64))
    url_host: Mapped[str] = mapped_column(String(255))
    last_attempt_at: Mapped[datetime | None]
    last_synced_at: Mapped[datetime | None]
    last_error: Mapped[str | None] = mapped_column(Text)
    busy_count: Mapped[int] = mapped_column(default=0, server_default=text("0"))


class DeadlineSuggestion(UUIDPrimaryKey, Timestamps, Base):
    """A due date found in a connected calendar. It becomes a task only if the student accepts."""

    __tablename__ = "deadline_suggestions"
    __table_args__ = (
        UniqueConstraint("feed_id", "external_uid"),
        Index(None, "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    feed_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("calendar_feeds.id", ondelete="CASCADE"))
    external_uid: Mapped[str] = mapped_column(String(500))
    title: Mapped[str] = mapped_column(String(200))
    due_at: Mapped[datetime]
    # A guess from the event's categories. Only the student's own courses are ever chosen.
    course_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("courses.id", ondelete="SET NULL")
    )
    status: Mapped[SuggestionStatus] = mapped_column(
        str_enum(SuggestionStatus, "suggestion_status"),
        default=SuggestionStatus.PENDING,
        server_default="pending",
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))

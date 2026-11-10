"""In-app notifications."""

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, UUIDPrimaryKey, str_enum
from app.models.enums import NotificationKind


class Notification(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "notifications"
    __table_args__ = (
        # Generating the same event twice is a harmless no-op with ON CONFLICT DO NOTHING.
        UniqueConstraint("user_id", "dedupe_key"),
        Index(None, "user_id", "created_at"),
        Index(None, "task_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[NotificationKind] = mapped_column(str_enum(NotificationKind, "notification_kind"))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    dedupe_key: Mapped[str] = mapped_column(String(200))
    task_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    read_at: Mapped[datetime | None]

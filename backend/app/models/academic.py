"""Courses and academic tasks."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPrimaryKey, str_enum
from app.models.enums import TaskStatus, TaskType


class Course(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "courses"
    __table_args__ = (
        # Redundant as a key, but required as the target of composite foreign keys.
        UniqueConstraint("id", "user_id"),
        CheckConstraint("color ~ '^#[0-9a-fA-F]{6}$'", name="color_hex"),
        Index(None, "user_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(120))
    code: Mapped[str | None] = mapped_column(String(32))
    description: Mapped[str | None] = mapped_column(Text)
    color: Mapped[str] = mapped_column(String(7))
    archived_at: Mapped[datetime | None]


class Task(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        UniqueConstraint("id", "user_id"),
        # Including user_id makes it impossible to attach a task to another user's course.
        ForeignKeyConstraint(
            ["course_id", "user_id"],
            ["courses.id", "courses.user_id"],
            name="fk_tasks_course_owner",
            ondelete="CASCADE",
        ),
        CheckConstraint("estimated_minutes > 0", name="estimated_positive"),
        CheckConstraint("remaining_minutes >= 0", name="remaining_non_negative"),
        CheckConstraint("actual_minutes >= 0", name="actual_non_negative"),
        CheckConstraint("priority BETWEEN 1 AND 4", name="priority_range"),
        CheckConstraint(
            "(status = 'completed') = (completed_at IS NOT NULL)", name="completed_at_matches"
        ),
        CheckConstraint(
            "(status = 'completed') = (remaining_minutes = 0)", name="remaining_matches_status"
        ),
        Index(None, "user_id", "status", "deadline_at"),
        Index(None, "course_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    course_id: Mapped[uuid.UUID | None]
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str | None] = mapped_column(Text)
    task_type: Mapped[TaskType] = mapped_column(str_enum(TaskType, "task_type"))
    # For exams this is the start of the exam. Null means the task has no due date.
    deadline_at: Mapped[datetime | None]
    estimated_minutes: Mapped[int]
    remaining_minutes: Mapped[int]
    actual_minutes: Mapped[int] = mapped_column(default=0, server_default=text("0"))
    priority: Mapped[int] = mapped_column(SmallInteger, default=2, server_default=text("2"))
    status: Mapped[TaskStatus] = mapped_column(
        str_enum(TaskStatus, "task_status"), default=TaskStatus.TODO, server_default="todo"
    )
    completed_at: Mapped[datetime | None]

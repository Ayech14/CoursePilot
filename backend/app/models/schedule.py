"""Study sessions, timers and schedule proposals."""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    column,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, ExcludeConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, CreatedAt, Timestamps, UUIDPrimaryKey, str_enum
from app.models.enums import (
    ChangeAction,
    ProposalStatus,
    ProposalTrigger,
    SessionOrigin,
    SessionStatus,
)


class StudySession(UUIDPrimaryKey, Timestamps, Base):
    __tablename__ = "study_sessions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["task_id", "user_id"],
            ["tasks.id", "tasks.user_id"],
            name="fk_study_sessions_task_owner",
            ondelete="CASCADE",
        ),
        CheckConstraint("start_at < end_at", name="ordered"),
        # The database itself guarantees a student is never booked twice. Deferrable so that
        # applying a proposal can swap two sessions within one transaction.
        ExcludeConstraint(
            ("user_id", "="),
            (func.tstzrange(column("start_at"), column("end_at")), "&&"),
            name="excl_study_sessions_no_overlap",
            using="gist",
            where=text("status IN ('planned', 'in_progress', 'paused')"),
            deferrable=True,
            initially="IMMEDIATE",
        ),
        Index(None, "user_id", "start_at"),
        Index(None, "task_id"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    task_id: Mapped[uuid.UUID]
    start_at: Mapped[datetime]
    end_at: Mapped[datetime]
    status: Mapped[SessionStatus] = mapped_column(
        str_enum(SessionStatus, "session_status"),
        default=SessionStatus.PLANNED,
        server_default="planned",
    )
    origin: Mapped[SessionOrigin] = mapped_column(str_enum(SessionOrigin, "session_origin"))
    is_locked: Mapped[bool] = mapped_column(default=False, server_default=text("false"))
    user_modified_at: Mapped[datetime | None]
    explanation: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    # Started on the spot with "Start timer" rather than planned ahead.
    unplanned: Mapped[bool] = mapped_column(default=False, server_default=text("false"))


class WorkInterval(UUIDPrimaryKey, Base):
    """One uninterrupted stretch of timed work. Pausing closes it; resuming opens another."""

    __tablename__ = "work_intervals"
    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR started_at <= ended_at", name="ordered"),
        Index(None, "session_id"),
        Index(
            "uq_work_intervals_one_running_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("ended_at IS NULL"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("study_sessions.id", ondelete="CASCADE")
    )
    started_at: Mapped[datetime]
    ended_at: Mapped[datetime | None]


class ScheduleProposal(UUIDPrimaryKey, CreatedAt, Base):
    __tablename__ = "schedule_proposals"
    __table_args__ = (
        Index(
            "uq_schedule_proposals_one_pending_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    trigger: Mapped[ProposalTrigger] = mapped_column(str_enum(ProposalTrigger, "proposal_trigger"))
    status: Mapped[ProposalStatus] = mapped_column(
        str_enum(ProposalStatus, "proposal_status"),
        default=ProposalStatus.PENDING,
        server_default="pending",
    )
    base_schedule_version: Mapped[int]
    summary: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    decided_at: Mapped[datetime | None]


class ProposalChange(UUIDPrimaryKey, Base):
    __tablename__ = "proposal_changes"
    __table_args__ = (
        CheckConstraint(
            "(action = 'create' AND before_start_at IS NULL AND after_start_at IS NOT NULL)"
            " OR (action = 'remove' AND before_start_at IS NOT NULL AND after_start_at IS NULL)"
            " OR (action IN ('move', 'resize')"
            " AND before_start_at IS NOT NULL AND after_start_at IS NOT NULL)",
            name="shape_matches_action",
        ),
        Index(None, "proposal_id"),
        Index(None, "session_id"),
        Index(None, "task_id"),
    )

    proposal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedule_proposals.id", ondelete="CASCADE")
    )
    action: Mapped[ChangeAction] = mapped_column(str_enum(ChangeAction, "change_action"))
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("study_sessions.id", ondelete="SET NULL")
    )
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))
    before_start_at: Mapped[datetime | None]
    before_end_at: Mapped[datetime | None]
    after_start_at: Mapped[datetime | None]
    after_end_at: Mapped[datetime | None]
    reason: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)

"""Connects the pure scheduling engine to the database.

The engine knows nothing about storage. This module translates rows into its input, stores its
output as a proposal, and applies a proposal exactly as the student previewed it.
"""

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import or_, select, text, update
from sqlalchemy.orm import Session

from app.core.errors import ProposalClosedError, ProposalStaleError
from app.models import (
    AvailabilityWindow,
    Course,
    OneOffBlock,
    ProposalChange,
    RecurringBlock,
    ScheduleProposal,
    StudyPreferences,
    StudySession,
    Task,
    User,
)
from app.models.enums import (
    ChangeAction,
    ProposalStatus,
    ProposalTrigger,
    SessionOrigin,
    SessionStatus,
    TaskStatus,
)
from app.schemas.schedule import (
    ApplyResult,
    AtRiskRead,
    ProposalChangeRead,
    ProposalRead,
    SessionRead,
    UnplacedRead,
)
from app.services.common import get_owned
from scheduler import plan
from scheduler.explain import describe_parts, describe_risk
from scheduler.models import (
    ExistingSession,
    Explanation,
    Interval,
    PlanRequest,
    PlanResult,
    Preferences,
    Reason,
    RiskReason,
    SessionClass,
    TaskInput,
    WeeklyTime,
)

logger = logging.getLogger(__name__)

_ACTIVE = (SessionStatus.PLANNED, SessionStatus.IN_PROGRESS, SessionStatus.PAUSED)
_MAX_LISTED_SESSIONS = 1000


def classify_session(session: StudySession, now: datetime) -> SessionClass:
    """How firmly the engine must respect a session. See DATABASE_DESIGN.md."""
    if session.is_locked or session.status != SessionStatus.PLANNED or session.start_at <= now:
        return SessionClass.LOCKED
    if session.origin == SessionOrigin.MANUAL or session.user_modified_at is not None:
        return SessionClass.STICKY
    return SessionClass.FLEXIBLE


def _active_future_sessions(db: Session, user: User, now: datetime) -> list[StudySession]:
    return list(
        db.scalars(
            select(StudySession).where(
                StudySession.user_id == user.id,
                StudySession.status.in_(_ACTIVE),
                StudySession.end_at > now,
            )
        )
    )


def _build_request(
    db: Session, user: User, now: datetime, sessions: Sequence[StudySession]
) -> PlanRequest:
    preferences = db.get_one(StudyPreferences, user.id)
    tasks = db.scalars(
        select(Task)
        .outerjoin(Course, Task.course_id == Course.id)
        .where(
            Task.user_id == user.id,
            Task.status != TaskStatus.COMPLETED,
            or_(Task.course_id.is_(None), Course.archived_at.is_(None)),
        )
    )
    windows = db.scalars(select(AvailabilityWindow).where(AvailabilityWindow.user_id == user.id))
    weekly = db.scalars(select(RecurringBlock).where(RecurringBlock.user_id == user.id))
    one_off = db.scalars(
        select(OneOffBlock).where(OneOffBlock.user_id == user.id, OneOffBlock.end_at > now)
    )
    return PlanRequest(
        now=now,
        timezone=user.timezone,
        horizon_end=now + timedelta(days=preferences.planning_horizon_days),
        tasks=tuple(
            TaskInput(
                id=str(task.id),
                remaining_minutes=task.remaining_minutes,
                priority=task.priority,
                deadline=task.deadline_at,
                course_id=None if task.course_id is None else str(task.course_id),
            )
            for task in tasks
        ),
        windows=tuple(WeeklyTime(w.day_of_week, w.start_minute, w.end_minute) for w in windows),
        weekly_blocks=tuple(
            WeeklyTime(b.day_of_week, b.start_minute, b.end_minute) for b in weekly
        ),
        one_off_blocks=tuple(Interval(b.start_at, b.end_at) for b in one_off),
        preferences=Preferences(
            preferred_session_minutes=preferences.preferred_session_minutes,
            min_session_minutes=preferences.min_session_minutes,
            break_minutes=preferences.break_minutes,
            max_daily_minutes=preferences.max_daily_minutes,
            deadline_buffer_hours=preferences.deadline_buffer_hours,
        ),
        existing_sessions=tuple(
            ExistingSession(
                str(s.id), str(s.task_id), s.start_at, s.end_at, classify_session(s, now)
            )
            for s in sessions
        ),
    )


def _explanation_json(explanation: Explanation) -> dict[str, Any]:
    return {
        "primary_reason": explanation.primary_reason.value,
        "factors": explanation.factors,
        "guard_override": explanation.guard_override,
        "deadline_at": explanation.deadline.isoformat() if explanation.deadline else None,
    }


def _explanation_text(stored: dict[str, Any] | None) -> str | None:
    if not stored or "primary_reason" not in stored:
        return None
    return describe_parts(Reason(stored["primary_reason"]), stored["factors"]["urgency"])


def _add_changes(
    db: Session,
    proposal: ScheduleProposal,
    result: PlanResult,
    flexible: Sequence[StudySession],
) -> tuple[int, int]:
    """Record what differs from today's schedule. Returns the counts of new and unchanged."""
    existing = {(str(s.task_id), s.start_at, s.end_at): s for s in flexible}
    unchanged = 0
    created = 0
    for placement in result.placements:
        if existing.pop((placement.task_id, placement.start, placement.end), None) is not None:
            unchanged += 1
            continue
        created += 1
        db.add(
            ProposalChange(
                proposal_id=proposal.id,
                action=ChangeAction.CREATE,
                task_id=uuid.UUID(placement.task_id),
                after_start_at=placement.start,
                after_end_at=placement.end,
                reason=_explanation_json(placement.explanation),
            )
        )
    for session in existing.values():
        db.add(
            ProposalChange(
                proposal_id=proposal.id,
                action=ChangeAction.REMOVE,
                session_id=session.id,
                task_id=session.task_id,
                before_start_at=session.start_at,
                before_end_at=session.end_at,
            )
        )
    return created, unchanged


def _close_pending(db: Session, user: User, now: datetime) -> None:
    db.execute(
        update(ScheduleProposal)
        .where(
            ScheduleProposal.user_id == user.id,
            ScheduleProposal.status == ProposalStatus.PENDING,
        )
        .values(status=ProposalStatus.SUPERSEDED, decided_at=now)
    )


def create_preview(db: Session, user: User, now: datetime) -> ProposalRead:
    """Plan and store a proposal. Nothing on the real schedule changes until it is applied."""
    sessions = _active_future_sessions(db, user, now)
    result = plan(_build_request(db, user, now, sessions))
    flexible = [s for s in sessions if classify_session(s, now) is SessionClass.FLEXIBLE]

    _close_pending(db, user, now)
    proposal = ScheduleProposal(
        user_id=user.id,
        trigger=ProposalTrigger.REGENERATE if flexible else ProposalTrigger.GENERATE,
        base_schedule_version=user.schedule_version,
        summary={},
    )
    db.add(proposal)
    db.flush()

    created, unchanged = _add_changes(db, proposal, result, flexible)
    proposal.summary = {
        "unchanged": unchanged,
        "at_risk": [
            {
                "task_id": item.task_id,
                "shortfall_minutes": item.shortfall_minutes,
                "reason": item.reason.value,
            }
            for item in result.at_risk
        ],
        "unplaced": [{"task_id": i.task_id, "minutes": i.minutes} for i in result.unplaced],
    }
    db.commit()
    logger.info(
        "schedule_previewed",
        extra={"user_id": str(user.id), "sessions_added": created, "at_risk": len(result.at_risk)},
    )
    return _to_read(db, proposal)


def _to_read(db: Session, proposal: ScheduleProposal) -> ProposalRead:
    rows = db.execute(
        select(ProposalChange, Task, Course)
        .join(Task, ProposalChange.task_id == Task.id)
        .outerjoin(Course, Task.course_id == Course.id)
        .where(ProposalChange.proposal_id == proposal.id)
        .order_by(
            ProposalChange.after_start_at.asc().nulls_last(),
            ProposalChange.before_start_at,
            ProposalChange.id,
        )
    ).all()
    changes = [
        ProposalChangeRead(
            id=change.id,
            action=change.action,
            session_id=change.session_id,
            task_id=change.task_id,
            task_title=task.title,
            course_name=course.name if course else None,
            course_color=course.color if course else None,
            before_start_at=change.before_start_at,
            before_end_at=change.before_end_at,
            after_start_at=change.after_start_at,
            after_end_at=change.after_end_at,
            explanation=_explanation_text(change.reason),
        )
        for change, task, course in rows
    ]

    summary = proposal.summary
    ids = [uuid.UUID(i["task_id"]) for i in (*summary["at_risk"], *summary["unplaced"])]
    tasks = {t.id: t for t in db.scalars(select(Task).where(Task.id.in_(ids)))} if ids else {}
    at_risk = [
        AtRiskRead(
            task_id=task.id,
            task_title=task.title,
            deadline_at=task.deadline_at,
            shortfall_minutes=item["shortfall_minutes"],
            reason=item["reason"],
            message=describe_risk(RiskReason(item["reason"])),
        )
        for item in summary["at_risk"]
        if (task := tasks.get(uuid.UUID(item["task_id"]))) is not None
    ]
    unplaced = [
        UnplacedRead(task_id=task.id, task_title=task.title, minutes=item["minutes"])
        for item in summary["unplaced"]
        if (task := tasks.get(uuid.UUID(item["task_id"]))) is not None
    ]
    return ProposalRead(
        id=proposal.id,
        trigger=proposal.trigger,
        status=proposal.status,
        created_at=proposal.created_at,
        unchanged_sessions=summary["unchanged"],
        at_risk=at_risk,
        unplaced=unplaced,
        changes=changes,
    )


def get_proposal(db: Session, user: User, proposal_id: uuid.UUID) -> ProposalRead:
    return _to_read(db, get_owned(db, ScheduleProposal, proposal_id, user.id))


def get_pending_proposal(db: Session, user: User) -> ProposalRead | None:
    proposal = db.scalar(
        select(ScheduleProposal).where(
            ScheduleProposal.user_id == user.id,
            ScheduleProposal.status == ProposalStatus.PENDING,
        )
    )
    return None if proposal is None else _to_read(db, proposal)


def _lock_user(db: Session, user: User) -> User:
    """Serialize changes to one student's schedule. Other students are unaffected."""
    return db.scalars(
        select(User)
        .where(User.id == user.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()


def _pending_or_raise(db: Session, user: User, proposal_id: uuid.UUID) -> ScheduleProposal:
    proposal = get_owned(db, ScheduleProposal, proposal_id, user.id)
    if proposal.status != ProposalStatus.PENDING:
        raise ProposalClosedError
    return proposal


def apply_proposal(db: Session, user: User, proposal_id: uuid.UUID, now: datetime) -> ApplyResult:
    locked = _lock_user(db, user)
    proposal = _pending_or_raise(db, locked, proposal_id)

    if proposal.base_schedule_version != locked.schedule_version:
        _expire(db, proposal, now)
        raise ProposalStaleError

    # A new session may take the place of one being removed, so check overlaps at the end.
    db.execute(text("SET CONSTRAINTS excl_study_sessions_no_overlap DEFERRED"))

    changes = db.scalars(select(ProposalChange).where(ProposalChange.proposal_id == proposal.id))
    created = removed = 0
    for change in changes:
        if change.action == ChangeAction.REMOVE:
            session = None if change.session_id is None else db.get(StudySession, change.session_id)
            if session is None or session.status != SessionStatus.PLANNED:
                db.rollback()
                _expire(db, _reload(db, proposal_id), now)
                raise ProposalStaleError
            session.status = SessionStatus.CANCELLED
            removed += 1
        else:
            db.add(
                StudySession(
                    user_id=locked.id,
                    task_id=change.task_id,
                    start_at=change.after_start_at,
                    end_at=change.after_end_at,
                    origin=SessionOrigin.AUTO,
                    explanation=change.reason,
                )
            )
            created += 1
    db.flush()
    # Raises here, inside this transaction, if anything still overlaps.
    db.execute(text("SET CONSTRAINTS excl_study_sessions_no_overlap IMMEDIATE"))

    proposal.status = ProposalStatus.APPLIED
    proposal.decided_at = now
    db.execute(
        update(User).where(User.id == locked.id).values(schedule_version=User.schedule_version + 1)
    )
    db.commit()
    logger.info("schedule_applied", extra={"user_id": str(locked.id), "sessions_added": created})
    return ApplyResult(created=created, removed=removed)


def _reload(db: Session, proposal_id: uuid.UUID) -> ScheduleProposal:
    return db.get_one(ScheduleProposal, proposal_id)


def _expire(db: Session, proposal: ScheduleProposal, now: datetime) -> None:
    proposal.status = ProposalStatus.SUPERSEDED
    proposal.decided_at = now
    db.commit()


def reject_proposal(db: Session, user: User, proposal_id: uuid.UUID, now: datetime) -> None:
    proposal = _pending_or_raise(db, user, proposal_id)
    proposal.status = ProposalStatus.REJECTED
    proposal.decided_at = now
    db.commit()


def list_sessions(
    db: Session, user: User, range_start: datetime, range_end: datetime
) -> list[SessionRead]:
    rows = db.execute(
        select(StudySession, Task, Course)
        .join(Task, StudySession.task_id == Task.id)
        .outerjoin(Course, Task.course_id == Course.id)
        .where(
            StudySession.user_id == user.id,
            StudySession.status != SessionStatus.CANCELLED,
            StudySession.end_at > range_start,
            StudySession.start_at < range_end,
        )
        .order_by(StudySession.start_at)
        .limit(_MAX_LISTED_SESSIONS)
    ).all()
    return [
        SessionRead(
            id=session.id,
            task_id=session.task_id,
            task_title=task.title,
            course_name=course.name if course else None,
            course_color=course.color if course else None,
            start_at=session.start_at,
            end_at=session.end_at,
            status=session.status,
            origin=session.origin,
            is_locked=session.is_locked,
            explanation=_explanation_text(session.explanation),
        )
        for session, task, course in rows
    ]


def utc_now() -> datetime:
    return datetime.now(UTC)

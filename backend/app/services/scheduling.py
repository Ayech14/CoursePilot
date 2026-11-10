"""Connects the pure scheduling engine to the database.

The engine knows nothing about storage. This module translates rows into its input, stores its
output as a proposal, and applies a proposal exactly as the student previewed it.
"""

import logging
import uuid
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from sqlalchemy import func, or_, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import ProposalClosedError, ProposalConflictError, ProposalStaleError
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
    WorkInterval,
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
    ApplyRequest,
    ApplyResult,
    AtRiskRead,
    ProposalChangeRead,
    ProposalRead,
    ScheduleStatus,
    SessionRead,
    UnplacedRead,
)
from app.services.common import get_owned, mark_schedule_inputs_changed
from scheduler.explain import describe_parts, describe_repair, describe_risk
from scheduler.models import (
    ChangeKind,
    ExistingSession,
    Explanation,
    Interval,
    PlanRequest,
    Preferences,
    Reason,
    RepairReason,
    RepairResult,
    RiskReason,
    SessionChange,
    SessionClass,
    TaskInput,
    WeeklyTime,
)
from scheduler.repair import rebuild, repair
from scheduler.timeline import local_to_utc

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = (SessionStatus.PLANNED, SessionStatus.IN_PROGRESS, SessionStatus.PAUSED)
_MAX_LISTED_SESSIONS = 1000
# A planned session this long past its end, and never started, counts as missed.
_MISSED_GRACE = timedelta(minutes=30)
_ENGINE_EXPLANATION_FIELDS = ("primary_reason", "factors", "guard_override", "deadline_at")


def classify_session(session: StudySession, now: datetime) -> SessionClass:
    """How firmly the engine must respect a session. See DATABASE_DESIGN.md."""
    if session.is_locked or session.status != SessionStatus.PLANNED or session.start_at <= now:
        return SessionClass.LOCKED
    if session.origin == SessionOrigin.MANUAL or session.user_modified_at is not None:
        return SessionClass.STICKY
    return SessionClass.FLEXIBLE


def active_future_sessions(db: Session, user: User, now: datetime) -> list[StudySession]:
    return list(
        db.scalars(
            select(StudySession).where(
                StudySession.user_id == user.id,
                StudySession.status.in_(ACTIVE_STATUSES),
                StudySession.end_at > now,
            )
        )
    )


def build_request(
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
        studied_today_minutes=_studied_today_minutes(db, user, now),
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


def local_day_bounds(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """The real instants a local date runs between. It need not be 24 hours long."""
    return local_to_utc(day, 0, zone), local_to_utc(day + timedelta(days=1), 0, zone)


def _studied_today_minutes(db: Session, user: User, now: datetime) -> int:
    """Timed work on finished sessions. Open sessions already count through their planned slot."""
    zone = ZoneInfo(user.timezone)
    day_start, day_end = local_day_bounds(now.astimezone(zone).date(), zone)
    rows = db.execute(
        select(WorkInterval.started_at, WorkInterval.ended_at)
        .join(StudySession, WorkInterval.session_id == StudySession.id)
        .where(
            WorkInterval.user_id == user.id,
            StudySession.status == SessionStatus.COMPLETED,
            WorkInterval.started_at < day_end,
            WorkInterval.ended_at > day_start,
        )
    ).all()
    seconds = sum(
        (min(ended, day_end) - max(started, day_start)).total_seconds() for started, ended in rows
    )
    return rounded_minutes(seconds)


def rounded_minutes(seconds: float) -> int:
    return int((seconds + 30) // 60)


def worked_minutes(
    db: Session, session_ids: Sequence[uuid.UUID], now: datetime
) -> dict[uuid.UUID, int]:
    """Timed work on each session, counting a timer that is still running."""
    if not session_ids:
        return {}
    rows = db.execute(
        select(WorkInterval.session_id, WorkInterval.started_at, WorkInterval.ended_at).where(
            WorkInterval.session_id.in_(session_ids)
        )
    ).all()
    seconds: dict[uuid.UUID, float] = defaultdict(float)
    for session_id, started, ended in rows:
        seconds[session_id] += ((ended or now) - started).total_seconds()
    return {session_id: rounded_minutes(total) for session_id, total in seconds.items()}


def _explanation_json(explanation: Explanation) -> dict[str, Any]:
    return {
        "primary_reason": explanation.primary_reason.value,
        "factors": explanation.factors,
        "guard_override": explanation.guard_override,
        "deadline_at": explanation.deadline.isoformat() if explanation.deadline else None,
    }


def _explanation_text(stored: dict[str, Any] | None) -> str | None:
    if not stored:
        return None
    if stored.get("repair_reason"):
        return describe_repair(RepairReason(stored["repair_reason"]))
    if "primary_reason" not in stored:
        return None
    return describe_parts(Reason(stored["primary_reason"]), stored["factors"]["urgency"])


def _change_json(change: SessionChange) -> dict[str, Any]:
    stored: dict[str, Any] = {}
    if change.explanation is not None:
        stored |= _explanation_json(change.explanation)
    if change.reason is not None:
        stored["repair_reason"] = change.reason.value
    if change.sticky_released:
        stored["sticky_released"] = True
    return stored


def _add_changes(db: Session, proposal: ScheduleProposal, outcome: RepairResult) -> None:
    for change in outcome.changes:
        before, after = change.before, change.after
        db.add(
            ProposalChange(
                proposal_id=proposal.id,
                action=ChangeAction(change.kind.value),
                session_id=uuid.UUID(change.session_id) if change.session_id else None,
                task_id=uuid.UUID(change.task_id),
                before_start_at=before.start if before else None,
                before_end_at=before.end if before else None,
                after_start_at=after.start if after else None,
                after_end_at=after.end if after else None,
                reason=_change_json(change),
            )
        )


def reconcile_missed_sessions(db: Session, user: User, now: datetime) -> None:
    """Mark planned sessions whose time has passed. Safe to run on every read."""
    result = db.execute(
        update(StudySession)
        .where(
            StudySession.user_id == user.id,
            StudySession.status == SessionStatus.PLANNED,
            StudySession.end_at < now - _MISSED_GRACE,
        )
        .values(status=SessionStatus.MISSED)
    )
    if result.rowcount:  # type: ignore[attr-defined]
        mark_schedule_inputs_changed(db, user.id)
        db.commit()
        db.refresh(user)
        logger.info("sessions_missed", extra={"user_id": str(user.id), "count": result.rowcount})  # type: ignore[attr-defined]


def _close_pending(db: Session, user: User, now: datetime) -> None:
    db.execute(
        update(ScheduleProposal)
        .where(
            ScheduleProposal.user_id == user.id,
            ScheduleProposal.status == ProposalStatus.PENDING,
        )
        .values(status=ProposalStatus.SUPERSEDED, decided_at=now)
    )


def create_preview(
    db: Session, user: User, now: datetime, mode: Literal["repair", "regenerate"] = "repair"
) -> ProposalRead:
    """Plan and store a proposal. Nothing on the real schedule changes until it is applied."""
    reconcile_missed_sessions(db, user, now)
    sessions = active_future_sessions(db, user, now)
    request = build_request(db, user, now, sessions)
    outcome = repair(request) if mode == "repair" else rebuild(request)

    if not sessions:
        trigger = ProposalTrigger.GENERATE
    elif mode == "repair":
        trigger = ProposalTrigger.MANUAL_REQUEST
    else:
        trigger = ProposalTrigger.REGENERATE

    _close_pending(db, user, now)
    proposal = ScheduleProposal(
        user_id=user.id,
        trigger=trigger,
        base_schedule_version=user.schedule_version,
        summary={
            "unchanged": outcome.unchanged,
            "stability_percent": (
                round(outcome.unchanged * 100 / len(sessions)) if sessions else 100
            ),
            "at_risk": [
                {
                    "task_id": item.task_id,
                    "shortfall_minutes": item.shortfall_minutes,
                    "reason": item.reason.value,
                }
                for item in outcome.at_risk
            ],
            "unplaced": [{"task_id": i.task_id, "minutes": i.minutes} for i in outcome.unplaced],
        },
    )
    db.add(proposal)
    db.flush()
    _add_changes(db, proposal, outcome)
    db.commit()
    logger.info(
        "schedule_previewed",
        extra={
            "user_id": str(user.id),
            "mode": mode,
            "changes": len(outcome.changes),
            "at_risk": len(outcome.at_risk),
        },
    )
    return _to_read(db, proposal)


def get_status(db: Session, user: User, now: datetime) -> ScheduleStatus:
    """Whether events since the last plan call for an update. Works it out; changes nothing."""
    reconcile_missed_sessions(db, user, now)
    sessions = active_future_sessions(db, user, now)
    outcome = repair(build_request(db, user, now, sessions))
    counts = dict.fromkeys(ChangeKind, 0)
    for change in outcome.changes:
        counts[change.kind] += 1

    last_applied = db.scalar(
        select(func.max(ScheduleProposal.decided_at)).where(
            ScheduleProposal.user_id == user.id,
            ScheduleProposal.status == ProposalStatus.APPLIED,
        )
    )
    missed_query = (
        select(func.count())
        .select_from(StudySession)
        .where(StudySession.user_id == user.id, StudySession.status == SessionStatus.MISSED)
    )
    if last_applied is not None:
        missed_query = missed_query.where(StudySession.end_at > last_applied)

    return ScheduleStatus(
        needs_update=bool(outcome.changes),
        added=counts[ChangeKind.CREATE],
        moved=counts[ChangeKind.MOVE],
        resized=counts[ChangeKind.RESIZE],
        removed=counts[ChangeKind.REMOVE],
        missed_sessions=db.scalar(missed_query) or 0,
        at_risk=len(outcome.at_risk),
    )


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
            sticky_released=bool(change.reason.get("sticky_released")),
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
        stability_percent=summary["stability_percent"],
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


def lock_user(db: Session, user: User) -> User:
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


def apply_proposal(
    db: Session, user: User, proposal_id: uuid.UUID, choices: ApplyRequest, now: datetime
) -> ApplyResult:
    """Apply a proposal, except for any individual changes the student turned down."""
    locked = lock_user(db, user)
    proposal = _pending_or_raise(db, locked, proposal_id)

    if proposal.base_schedule_version != locked.schedule_version:
        _expire(db, proposal, now)
        raise ProposalStaleError

    # A session may take the place of one being moved, so overlaps are checked at the end.
    db.execute(text("SET CONSTRAINTS excl_study_sessions_no_overlap DEFERRED"))

    rejected = set(choices.rejected_change_ids)
    counts = dict.fromkeys(ChangeAction, 0)
    skipped = 0
    changes = db.scalars(select(ProposalChange).where(ProposalChange.proposal_id == proposal.id))
    for change in changes:
        if change.id in rejected:
            skipped += 1
            continue
        counts[change.action] += 1
        if change.action == ChangeAction.CREATE:
            db.add(
                StudySession(
                    user_id=locked.id,
                    task_id=change.task_id,
                    start_at=change.after_start_at,
                    end_at=change.after_end_at,
                    origin=SessionOrigin.AUTO,
                    explanation=_engine_explanation(change),
                )
            )
            continue

        session = None if change.session_id is None else db.get(StudySession, change.session_id)
        if (
            session is None
            or session.status != SessionStatus.PLANNED
            or (session.start_at, session.end_at) != (change.before_start_at, change.before_end_at)
        ):
            db.rollback()
            _expire(db, _reload(db, proposal_id), now)
            raise ProposalStaleError
        if change.action == ChangeAction.REMOVE:
            session.status = SessionStatus.CANCELLED
        else:
            assert change.after_start_at is not None  # noqa: S101  # Guaranteed by a CHECK.
            assert change.after_end_at is not None  # noqa: S101
            session.start_at = change.after_start_at
            session.end_at = change.after_end_at
            if change.action == ChangeAction.MOVE:
                session.explanation = _engine_explanation(change)

    try:
        db.flush()
        # Raises here, inside this transaction, if anything still overlaps.
        db.execute(text("SET CONSTRAINTS excl_study_sessions_no_overlap IMMEDIATE"))
    except IntegrityError as exc:
        db.rollback()
        if rejected:
            raise ProposalConflictError from exc
        raise

    proposal.status = ProposalStatus.APPLIED
    proposal.decided_at = now
    mark_schedule_inputs_changed(db, locked.id)
    db.commit()
    logger.info("schedule_applied", extra={"user_id": str(locked.id), "skipped": skipped})
    return ApplyResult(
        created=counts[ChangeAction.CREATE],
        moved=counts[ChangeAction.MOVE],
        resized=counts[ChangeAction.RESIZE],
        removed=counts[ChangeAction.REMOVE],
        skipped=skipped,
    )


def _engine_explanation(change: ProposalChange) -> dict[str, Any] | None:
    """What a session keeps: why it is here, not why it had to change."""
    kept = {k: v for k, v in change.reason.items() if k in _ENGINE_EXPLANATION_FIELDS}
    return kept or None


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


def session_read(
    session: StudySession, task: Task, course: Course | None, actual_minutes: int = 0
) -> SessionRead:
    return SessionRead(
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
        is_user_modified=(
            session.origin == SessionOrigin.MANUAL or session.user_modified_at is not None
        ),
        explanation=_explanation_text(session.explanation),
        actual_minutes=actual_minutes,
    )


def list_sessions(
    db: Session, user: User, now: datetime, range_start: datetime, range_end: datetime
) -> list[SessionRead]:
    reconcile_missed_sessions(db, user, now)
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
    worked = worked_minutes(db, [row[0].id for row in rows], now)
    return [
        session_read(session, task, course, worked.get(session.id, 0))
        for session, task, course in rows
    ]


def utc_now() -> datetime:
    return datetime.now(UTC)

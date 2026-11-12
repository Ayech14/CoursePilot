"""The study timer: start, pause, resume, finish.

Work intervals are the single record of time actually studied. Pausing closes one and resuming
opens another, so every figure in analytics can be traced back to real stretches of work.

A running session keeps its planned slot on the calendar. Actual time lives in the intervals.
"""

import logging
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import (
    InvalidFieldsError,
    SessionConflictError,
    SessionNotStartableError,
    TaskCompletedError,
    TimerActiveError,
    TimerStateError,
)
from app.models import StudyPreferences, StudySession, Task, User, WorkInterval
from app.models.enums import SessionOrigin, SessionStatus, TaskStatus
from app.schemas.schedule import ActiveTimerRead, SessionRead, TimerFinish
from app.services.common import get_owned, mark_schedule_inputs_changed
from app.services.scheduling import lock_user, reconcile_missed_sessions, rounded_minutes
from app.services.sessions import read_session
from app.services.tasks import apply_work

logger = logging.getLogger(__name__)

_OPEN = (SessionStatus.IN_PROGRESS, SessionStatus.PAUSED)
_SHORTEST_SLOT = timedelta(minutes=1)


def _intervals(db: Session, session: StudySession) -> list[WorkInterval]:
    return list(
        db.scalars(
            select(WorkInterval)
            .where(WorkInterval.session_id == session.id)
            .order_by(WorkInterval.started_at)
        )
    )


def _seconds(intervals: list[WorkInterval], now: datetime) -> float:
    return sum(((i.ended_at or now) - i.started_at).total_seconds() for i in intervals)


def _timer_read(db: Session, session: StudySession, now: datetime) -> ActiveTimerRead:
    return ActiveTimerRead(
        session=read_session(db, session, now),
        running=session.status == SessionStatus.IN_PROGRESS,
        elapsed_seconds=int(_seconds(_intervals(db, session), now)),
    )


def _open_session(db: Session, user: User) -> StudySession | None:
    return db.scalar(
        select(StudySession)
        .where(StudySession.user_id == user.id, StudySession.status.in_(_OPEN))
        .order_by(StudySession.start_at)
        .limit(1)
    )


def _close_running(intervals: list[WorkInterval], now: datetime) -> None:
    for interval in intervals:
        if interval.ended_at is None:
            # The bound protects the ordering constraint if the server clock steps backwards.
            interval.ended_at = max(now, interval.started_at)


def _in_status(
    db: Session, user: User, session_id: uuid.UUID, *allowed: SessionStatus
) -> StudySession:
    session = get_owned(db, StudySession, session_id, user.id)
    if session.status not in allowed:
        raise TimerStateError
    return session


def get_active(db: Session, user: User, now: datetime) -> ActiveTimerRead | None:
    session = _open_session(db, user)
    return None if session is None else _timer_read(db, session, now)


def _begin(db: Session, user: User, session: StudySession, now: datetime) -> ActiveTimerRead:
    task = db.get_one(Task, session.task_id)
    if task.status == TaskStatus.COMPLETED:
        raise TaskCompletedError
    if task.status == TaskStatus.TODO:
        task.status = TaskStatus.IN_PROGRESS

    session.status = SessionStatus.IN_PROGRESS
    db.add(WorkInterval(user_id=user.id, session_id=session.id, started_at=now))
    mark_schedule_inputs_changed(db, user.id)
    db.commit()
    logger.info("timer_started", extra={"user_id": str(user.id), "session_id": str(session.id)})
    return _timer_read(db, session, now)


def start(db: Session, user: User, session_id: uuid.UUID, now: datetime) -> ActiveTimerRead:
    reconcile_missed_sessions(db, user, now)
    locked = lock_user(db, user)
    session = _in_status(db, locked, session_id, SessionStatus.PLANNED)
    if _open_session(db, locked) is not None:
        raise TimerActiveError

    zone = ZoneInfo(locked.timezone)
    if session.start_at.astimezone(zone).date() > now.astimezone(zone).date():
        raise SessionNotStartableError
    return _begin(db, locked, session, now)


def quick_start(db: Session, user: User, task_id: uuid.UUID, now: datetime) -> ActiveTimerRead:
    """Time a task right now, without planning a session first.

    The new session holds the calendar from now for one preferred session length, or until the
    next planned session, so the scheduler sees the time as taken. Finishing it shrinks the slot
    to the time actually worked.
    """
    reconcile_missed_sessions(db, user, now)
    locked = lock_user(db, user)
    if _open_session(db, locked) is not None:
        raise TimerActiveError
    task = get_owned(db, Task, task_id, locked.id)
    if task.status == TaskStatus.COMPLETED:
        raise TaskCompletedError

    planned = db.scalars(
        select(StudySession)
        .where(
            StudySession.user_id == locked.id,
            StudySession.status == SessionStatus.PLANNED,
            StudySession.end_at > now,
        )
        .order_by(StudySession.start_at)
    ).first()
    if planned is not None and planned.start_at <= now:
        # A session is planned for right now. If it is for this task, that is the one to time.
        if planned.task_id == task.id:
            return _begin(db, locked, planned, now)
        title = db.get_one(Task, planned.task_id).title
        raise SessionConflictError(
            f"You have \u201c{title}\u201d planned right now. Start that session, or move it first."
        )

    preferences = db.get(StudyPreferences, locked.id)
    length = timedelta(minutes=preferences.preferred_session_minutes if preferences else 50)
    end = now + length if planned is None else min(now + length, planned.start_at)
    if end - now < _SHORTEST_SLOT:
        raise SessionConflictError(
            "Your next planned session starts in under a minute. Start that one instead."
        )
    session = StudySession(
        user_id=locked.id,
        task_id=task.id,
        start_at=now,
        end_at=end,
        origin=SessionOrigin.MANUAL,
        unplanned=True,
    )
    db.add(session)
    db.flush()
    return _begin(db, locked, session, now)


def pause(db: Session, user: User, session_id: uuid.UUID, now: datetime) -> ActiveTimerRead:
    locked = lock_user(db, user)
    session = _in_status(db, locked, session_id, SessionStatus.IN_PROGRESS)
    _close_running(_intervals(db, session), now)
    session.status = SessionStatus.PAUSED
    db.commit()
    return _timer_read(db, session, now)


def resume(db: Session, user: User, session_id: uuid.UUID, now: datetime) -> ActiveTimerRead:
    locked = lock_user(db, user)
    session = _in_status(db, locked, session_id, SessionStatus.PAUSED)
    session.status = SessionStatus.IN_PROGRESS
    db.add(WorkInterval(user_id=locked.id, session_id=session.id, started_at=now))
    db.commit()
    return _timer_read(db, session, now)


def _trim_to(intervals: list[WorkInterval], excess_seconds: float) -> None:
    """Take time off the end of the work, for a timer that kept running after the student left."""
    for interval in reversed(intervals):
        if excess_seconds <= 0:
            return
        assert interval.ended_at is not None  # noqa: S101  # All intervals are closed by now.
        length = (interval.ended_at - interval.started_at).total_seconds()
        cut = min(length, excess_seconds)
        interval.ended_at -= timedelta(seconds=cut)
        excess_seconds -= cut


def finish(
    db: Session, user: User, session_id: uuid.UUID, outcome: TimerFinish, now: datetime
) -> SessionRead:
    """End the session and credit the time to its task."""
    locked = lock_user(db, user)
    session = _in_status(db, locked, session_id, *_OPEN)
    intervals = _intervals(db, session)
    _close_running(intervals, now)

    seconds = _seconds(intervals, now)
    minutes = rounded_minutes(seconds)
    if outcome.actual_minutes is not None and outcome.actual_minutes != minutes:
        if outcome.actual_minutes > minutes:
            raise InvalidFieldsError(
                {"actual_minutes": f"The timer recorded {minutes} minutes. Enter that or less."}
            )
        _trim_to(intervals, seconds - outcome.actual_minutes * 60)
        minutes = outcome.actual_minutes

    task = db.get_one(Task, session.task_id)
    if task.status == TaskStatus.COMPLETED:
        # Finished elsewhere while the timer ran. The time was still spent.
        task.actual_minutes += minutes
    else:
        apply_work(
            task,
            minutes_spent=minutes,
            remaining=outcome.remaining_minutes,
            mark_completed=outcome.mark_task_completed,
            now=now,
        )

    session.status = SessionStatus.COMPLETED
    if session.unplanned:
        # The slot was a guess made at the start. Now the real end is known.
        last_end = max((i.ended_at for i in intervals if i.ended_at), default=session.start_at)
        session.end_at = max(last_end, session.start_at + _SHORTEST_SLOT)
    mark_schedule_inputs_changed(db, locked.id)
    db.commit()
    logger.info(
        "timer_finished",
        extra={"user_id": str(locked.id), "session_id": str(session.id), "minutes": minutes},
    )
    return read_session(db, session, now)


def discard(db: Session, user: User, session_id: uuid.UUID) -> None:
    """Undo an accidental start. No time is recorded.

    A planned session goes back to planned. One started on the spot never existed before, so it
    is removed rather than left behind as a planned session.
    """
    locked = lock_user(db, user)
    session = _in_status(db, locked, session_id, *_OPEN)
    db.execute(delete(WorkInterval).where(WorkInterval.session_id == session.id))
    if session.unplanned:
        db.delete(session)
    else:
        session.status = SessionStatus.PLANNED
    mark_schedule_inputs_changed(db, locked.id)
    db.commit()

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
    SessionNotStartableError,
    TaskCompletedError,
    TimerActiveError,
    TimerStateError,
)
from app.models import StudySession, Task, User, WorkInterval
from app.models.enums import SessionStatus, TaskStatus
from app.schemas.schedule import ActiveTimerRead, SessionRead, TimerFinish
from app.services.common import get_owned, mark_schedule_inputs_changed
from app.services.scheduling import lock_user, reconcile_missed_sessions, rounded_minutes
from app.services.sessions import read_session
from app.services.tasks import apply_work

logger = logging.getLogger(__name__)

_OPEN = (SessionStatus.IN_PROGRESS, SessionStatus.PAUSED)


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


def start(db: Session, user: User, session_id: uuid.UUID, now: datetime) -> ActiveTimerRead:
    reconcile_missed_sessions(db, user, now)
    locked = lock_user(db, user)
    session = _in_status(db, locked, session_id, SessionStatus.PLANNED)
    if _open_session(db, locked) is not None:
        raise TimerActiveError

    zone = ZoneInfo(locked.timezone)
    if session.start_at.astimezone(zone).date() > now.astimezone(zone).date():
        raise SessionNotStartableError

    task = db.get_one(Task, session.task_id)
    if task.status == TaskStatus.COMPLETED:
        raise TaskCompletedError
    if task.status == TaskStatus.TODO:
        task.status = TaskStatus.IN_PROGRESS

    session.status = SessionStatus.IN_PROGRESS
    db.add(WorkInterval(user_id=locked.id, session_id=session.id, started_at=now))
    mark_schedule_inputs_changed(db, locked.id)
    db.commit()
    logger.info("timer_started", extra={"user_id": str(locked.id), "session_id": str(session.id)})
    return _timer_read(db, session, now)


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
    mark_schedule_inputs_changed(db, locked.id)
    db.commit()
    logger.info(
        "timer_finished",
        extra={"user_id": str(locked.id), "session_id": str(session.id), "minutes": minutes},
    )
    return read_session(db, session, now)


def discard(db: Session, user: User, session_id: uuid.UUID) -> None:
    """Undo an accidental start. The session goes back to planned and no time is recorded."""
    locked = lock_user(db, user)
    session = _in_status(db, locked, session_id, *_OPEN)
    db.execute(delete(WorkInterval).where(WorkInterval.session_id == session.id))
    session.status = SessionStatus.PLANNED
    mark_schedule_inputs_changed(db, locked.id)
    db.commit()

"""In-app notifications (PRD I1 to I3).

There is no background worker. Notifications are worked out when the student asks for them,
which the app does when it opens and every few minutes while it is open. Each one has a key that
names the event, such as "overdue:<task>:<deadline>", and the database refuses a second row with
the same key, so working them out again never repeats one (I3). A changed deadline is a new event.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import AvailabilityWindow, Notification, StudySession, Task, User
from app.models.enums import NotificationKind, SessionStatus, TaskStatus
from app.schemas.notification import NotificationList, NotificationRead
from app.services.common import get_owned
from app.services.insights import attention
from app.services.scheduling import get_status, reconcile_missed_sessions

logger = logging.getLogger(__name__)

_LIST_LIMIT = 50
_MISSED_LOOKBACK = timedelta(days=7)


@dataclass(frozen=True)
class _Event:
    kind: NotificationKind
    key: str
    title: str
    body: str
    task_id: uuid.UUID | None = None


def _when(instant: datetime, zone: ZoneInfo) -> str:
    """ "Thu, Nov 12 at 9:10 PM", in the student's zone."""
    local = instant.astimezone(zone)
    hour = local.hour % 12 or 12
    return f"{local:%a, %b} {local.day} at {hour}:{local:%M} {'AM' if local.hour < 12 else 'PM'}"


def _duration(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    if not hours:
        return f"{rest}m"
    return f"{hours}h" if not rest else f"{hours}h {rest}m"


def _has_study_hours(db: Session, user: User) -> bool:
    count = db.scalar(
        select(func.count())
        .select_from(AvailabilityWindow)
        .where(AvailabilityWindow.user_id == user.id)
    )
    return bool(count)


def _task_events(db: Session, user: User, now: datetime, zone: ZoneInfo) -> list[_Event]:
    has_hours = _has_study_hours(db, user)
    remaining: dict[uuid.UUID, int] = dict(
        db.execute(
            select(Task.id, Task.remaining_minutes).where(
                Task.user_id == user.id, Task.status != TaskStatus.COMPLETED
            )
        )
        .tuples()
        .all()
    )
    events: list[_Event] = []
    short_of_time = 0
    for item in attention(db, user, now):
        due = item.deadline_at.isoformat()
        when = _when(item.deadline_at, zone)
        if item.reason == "overdue":
            events.append(
                _Event(
                    NotificationKind.TASK_OVERDUE,
                    f"overdue:{item.task_id}:{due}",
                    f"{item.title} is overdue",
                    f"It was due {when}. Mark it finished, or give it a new deadline so it can "
                    "be planned again.",
                    item.task_id,
                )
            )
        elif item.reason == "not_fully_planned":
            short_of_time += 1
            if has_hours:
                events.append(
                    _Event(
                        NotificationKind.WORKLOAD_CONFLICT,
                        f"short:{item.task_id}:{due}",
                        f"Not enough time planned for {item.title}",
                        f"{_duration(item.unplanned_minutes)} of work is not in your schedule "
                        f"before it is due {when}. Update your schedule, or add study hours.",
                        item.task_id,
                    )
                )
        else:
            events.append(
                _Event(
                    NotificationKind.DEADLINE_APPROACHING,
                    f"due:{item.task_id}:{due}",
                    f"{item.title} is due soon",
                    f"Due {when}, with {_duration(remaining.get(item.task_id, 0))} of work left.",
                    item.task_id,
                )
            )
    if short_of_time and not has_hours:
        # One clear cause beats a notification per task that all say the same thing.
        events.append(
            _Event(
                NotificationKind.WORKLOAD_CONFLICT,
                "no-study-hours",
                "Nothing can be scheduled yet",
                f"{short_of_time} task{'s need' if short_of_time > 1 else ' needs'} study time, "
                "but you have not set any weekly study hours. Add them on the Your week page.",
            )
        )
    return events


def _missed_events(db: Session, user: User, now: datetime, zone: ZoneInfo) -> list[_Event]:
    rows = db.execute(
        select(StudySession, Task)
        .join(Task, StudySession.task_id == Task.id)
        .where(
            StudySession.user_id == user.id,
            StudySession.status == SessionStatus.MISSED,
            StudySession.end_at > now - _MISSED_LOOKBACK,
            Task.status != TaskStatus.COMPLETED,
        )
    ).all()
    return [
        _Event(
            NotificationKind.TASK_UNFINISHED,
            f"missed:{session.id}",
            f"Missed session for {task.title}",
            f"The session {_when(session.start_at, zone)} was not started. Update your schedule "
            "to make up the time.",
            task.id,
        )
        for session, task in rows
    ]


def _schedule_event(db: Session, user: User, now: datetime) -> list[_Event]:
    status = get_status(db, user, now)
    if not status.needs_update:
        return []
    changes = status.added + status.moved + status.resized + status.removed
    body = f"{changes} suggested change{'s' if changes != 1 else ''}"
    missed = status.missed_sessions
    if missed:
        body = f"{missed} missed session{'s' if missed != 1 else ''} and {body}"
    return [
        _Event(
            NotificationKind.SCHEDULE_ADJUSTED,
            # One per version of the student's inputs: a new change after this one is a new event.
            f"schedule:{user.schedule_version}",
            "Your schedule needs an update",
            f"{body}. Review them on the Schedule page before anything changes.",
        )
    ]


def reconcile(db: Session, user: User, now: datetime) -> int:
    """Record any new events. Running it again with nothing new does nothing."""
    zone = ZoneInfo(user.timezone)
    # First, so that a session that has just been missed is reported now, not on the next visit.
    reconcile_missed_sessions(db, user, now)
    events = [
        *_missed_events(db, user, now, zone),
        *_task_events(db, user, now, zone),
        *_schedule_event(db, user, now),
    ]
    if not events:
        return 0
    created = db.scalars(
        insert(Notification)
        .values(
            [
                {
                    "id": uuid.uuid7(),
                    "user_id": user.id,
                    "kind": event.kind,
                    "title": event.title[:200],
                    "body": event.body,
                    "dedupe_key": event.key[:200],
                    "task_id": event.task_id,
                    "created_at": now,
                }
                for event in events
            ]
        )
        .on_conflict_do_nothing(index_elements=["user_id", "dedupe_key"])
        .returning(Notification.id)
    ).all()
    db.commit()
    if created:
        logger.info("notifications_created", extra={"user_id": str(user.id), "count": len(created)})
    return len(created)


def list_notifications(db: Session, user: User, now: datetime) -> NotificationList:
    reconcile(db, user, now)
    items = db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(_LIST_LIMIT)
    )
    unread = db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )
    return NotificationList(
        items=[NotificationRead.model_validate(item) for item in items], unread=unread or 0
    )


def mark_read(
    db: Session, user: User, notification_id: uuid.UUID, now: datetime
) -> NotificationRead:
    notification = get_owned(db, Notification, notification_id, user.id)
    if notification.read_at is None:
        notification.read_at = now
        db.commit()
    return NotificationRead.model_validate(notification)


def mark_all_read(db: Session, user: User, now: datetime) -> None:
    db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=now)
    )
    db.commit()

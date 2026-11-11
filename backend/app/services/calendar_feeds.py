"""Connected calendars: adding, syncing, and turning their deadlines into task suggestions.

There is no background worker. A feed syncs when it is added, when the student asks, and when the
app finds it older than six hours, the same lazy approach as missed sessions.
"""

import logging
import re
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.errors import InvalidFieldsError, SuggestionClosedError
from app.models import (
    CalendarFeed,
    Course,
    DeadlineSuggestion,
    OneOffBlock,
    RecurringBlock,
    StudyPreferences,
    User,
)
from app.models.enums import SuggestionStatus
from app.schemas.calendar import (
    BusyRead,
    FeedCreate,
    FeedRead,
    SuggestionAccept,
    SuggestionRead,
)
from app.schemas.task import TaskCreate
from app.services import feed_fetch, ics
from app.services.common import get_owned, mark_schedule_inputs_changed
from app.services.tasks import create_task
from scheduler.models import WeeklyTime
from scheduler.timeline import expand_rules

logger = logging.getLogger(__name__)

MAX_FEEDS = 10
STALE_AFTER = timedelta(hours=6)
_LOOKBACK = timedelta(days=1)
_EXTRA_DAYS = 7
_MAX_BUSY_RANGE = timedelta(days=62)


def _url_hint(url: str) -> str:
    return f"{urlsplit(url).hostname}/…"


def _read(db: Session, feed: CalendarFeed) -> FeedRead:
    pending = db.scalar(
        select(func.count())
        .select_from(DeadlineSuggestion)
        .where(
            DeadlineSuggestion.feed_id == feed.id,
            DeadlineSuggestion.status == SuggestionStatus.PENDING,
        )
    )
    return FeedRead(
        id=feed.id,
        name=feed.name,
        url_hint=_url_hint(feed.url),
        last_synced_at=feed.last_synced_at,
        last_error=feed.last_error,
        busy_count=feed.busy_count,
        pending_deadlines=pending or 0,
    )


def _feeds(db: Session, user: User) -> list[CalendarFeed]:
    return list(
        db.scalars(
            select(CalendarFeed)
            .where(CalendarFeed.user_id == user.id)
            .order_by(CalendarFeed.created_at, CalendarFeed.id)
        )
    )


def list_feeds(db: Session, user: User) -> list[FeedRead]:
    return [_read(db, feed) for feed in _feeds(db, user)]


def _normalized(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", value.upper())


def _guess_course(courses: list[Course], hints: tuple[str, ...], title: str) -> uuid.UUID | None:
    """Match a course code inside the event's categories or title, preferring the longest code."""
    haystacks = [_normalized(text) for text in (*hints, title)]
    candidates = [
        course
        for course in courses
        if course.code and (code := _normalized(course.code)) and any(code in h for h in haystacks)
    ]
    best = max(candidates, key=lambda c: len(_normalized(c.code or "")), default=None)
    return None if best is None else best.id


def _replace_busy(db: Session, user: User, feed: CalendarFeed, busy: list[ics.BusyEvent]) -> bool:
    current = {
        (b.external_uid, b.start_at, b.end_at, b.title)
        for b in db.scalars(select(OneOffBlock).where(OneOffBlock.feed_id == feed.id))
    }
    incoming = {(e.uid, e.start, e.end, e.title) for e in busy}
    if current == incoming:
        return False
    db.execute(delete(OneOffBlock).where(OneOffBlock.feed_id == feed.id))
    db.add_all(
        OneOffBlock(
            user_id=user.id,
            feed_id=feed.id,
            external_uid=uid,
            title=title,
            start_at=start,
            end_at=end,
        )
        for uid, start, end, title in incoming
    )
    return True


def _merge_deadlines(
    db: Session, user: User, feed: CalendarFeed, deadlines: list[ics.DeadlineEvent], now: datetime
) -> None:
    existing = {
        s.external_uid: s
        for s in db.scalars(select(DeadlineSuggestion).where(DeadlineSuggestion.feed_id == feed.id))
    }
    courses = list(
        db.scalars(select(Course).where(Course.user_id == user.id, Course.archived_at.is_(None)))
    )
    seen: set[str] = set()
    for event in deadlines:
        if event.due <= now:
            continue
        seen.add(event.uid)
        suggestion = existing.get(event.uid)
        if suggestion is None:
            db.add(
                DeadlineSuggestion(
                    user_id=user.id,
                    feed_id=feed.id,
                    external_uid=event.uid,
                    title=event.title,
                    due_at=event.due,
                    course_id=_guess_course(courses, event.hints, event.title),
                )
            )
        elif suggestion.status == SuggestionStatus.PENDING:
            # Decided suggestions keep what the student saw when they decided.
            suggestion.title = event.title
            suggestion.due_at = event.due
    # A pending suggestion whose event vanished or passed is no longer worth asking about.
    for uid, suggestion in existing.items():
        if uid not in seen and suggestion.status == SuggestionStatus.PENDING:
            db.delete(suggestion)


def _sync(db: Session, user: User, feed: CalendarFeed, now: datetime) -> bool:
    """Fetch and apply one feed. On failure the previous events stay, and the error is recorded."""
    feed.last_attempt_at = now
    horizon = db.get_one(StudyPreferences, user.id).planning_horizon_days + _EXTRA_DAYS
    try:
        data = feed_fetch.fetch_calendar(feed.url)
        parsed = ics.parse(
            data, ZoneInfo(user.timezone), now - _LOOKBACK, now + timedelta(days=horizon)
        )
    except (feed_fetch.FeedFetchError, ics.IcsError) as exc:
        feed.last_error = str(exc)
        logger.info("feed_sync_failed", extra={"user_id": str(user.id), "feed_id": str(feed.id)})
        return False

    if _replace_busy(db, user, feed, parsed.busy):
        mark_schedule_inputs_changed(db, user.id)
    _merge_deadlines(db, user, feed, parsed.deadlines, now)
    feed.busy_count = len(parsed.busy)
    feed.last_error = None
    feed.last_synced_at = now
    logger.info(
        "feed_synced",
        extra={
            "user_id": str(user.id),
            "feed_id": str(feed.id),
            "busy": len(parsed.busy),
            "deadlines": len(parsed.deadlines),
        },
    )
    return True


def create_feed(db: Session, user: User, data: FeedCreate, now: datetime) -> FeedRead:
    if len(_feeds(db, user)) >= MAX_FEEDS:
        raise InvalidFieldsError({"url": f"You can connect up to {MAX_FEEDS} calendars."})
    try:
        url = feed_fetch.normalize_url(data.url)
    except feed_fetch.FeedFetchError as exc:
        raise InvalidFieldsError({"url": str(exc)}) from exc
    duplicate = db.scalar(
        select(CalendarFeed.id).where(CalendarFeed.user_id == user.id, CalendarFeed.url == url)
    )
    if duplicate is not None:
        raise InvalidFieldsError({"url": "This calendar is already connected."})

    feed = CalendarFeed(user_id=user.id, name=data.name, url=url)
    db.add(feed)
    db.flush()
    if not _sync(db, user, feed, now):
        message = feed.last_error or "We could not read that calendar."
        db.rollback()
        raise InvalidFieldsError({"url": message})
    db.commit()
    return _read(db, feed)


def rename_feed(db: Session, user: User, feed_id: uuid.UUID, name: str) -> FeedRead:
    feed = get_owned(db, CalendarFeed, feed_id, user.id)
    feed.name = name
    db.commit()
    return _read(db, feed)


def sync_feed(db: Session, user: User, feed_id: uuid.UUID, now: datetime) -> FeedRead:
    feed = get_owned(db, CalendarFeed, feed_id, user.id)
    _sync(db, user, feed, now)
    db.commit()
    return _read(db, feed)


def sync_stale(db: Session, user: User, now: datetime) -> list[FeedRead]:
    for feed in _feeds(db, user):
        if feed.last_attempt_at is None or feed.last_attempt_at < now - STALE_AFTER:
            _sync(db, user, feed, now)
    db.commit()
    return list_feeds(db, user)


def delete_feed(db: Session, user: User, feed_id: uuid.UUID) -> None:
    """Its busy times and open suggestions go too. Tasks already accepted stay."""
    feed = get_owned(db, CalendarFeed, feed_id, user.id)
    if feed.busy_count:
        mark_schedule_inputs_changed(db, user.id)
    db.delete(feed)
    db.commit()


def list_suggestions(db: Session, user: User, now: datetime) -> list[SuggestionRead]:
    rows = db.execute(
        select(DeadlineSuggestion, CalendarFeed.name, Course.name)
        .join(CalendarFeed, DeadlineSuggestion.feed_id == CalendarFeed.id)
        .outerjoin(Course, DeadlineSuggestion.course_id == Course.id)
        .where(
            DeadlineSuggestion.user_id == user.id,
            DeadlineSuggestion.status == SuggestionStatus.PENDING,
            DeadlineSuggestion.due_at > now,
        )
        .order_by(DeadlineSuggestion.due_at, DeadlineSuggestion.id)
    ).all()
    return [
        SuggestionRead(
            id=suggestion.id,
            title=suggestion.title,
            due_at=suggestion.due_at,
            feed_name=feed_name,
            course_id=suggestion.course_id,
            course_name=course_name,
        )
        for suggestion, feed_name, course_name in rows
    ]


def _pending(db: Session, user: User, suggestion_id: uuid.UUID) -> DeadlineSuggestion:
    suggestion = get_owned(db, DeadlineSuggestion, suggestion_id, user.id)
    if suggestion.status != SuggestionStatus.PENDING:
        raise SuggestionClosedError
    return suggestion


def accept_suggestion(
    db: Session, user: User, suggestion_id: uuid.UUID, choice: SuggestionAccept
) -> uuid.UUID:
    suggestion = _pending(db, user, suggestion_id)
    task = create_task(
        db,
        user,
        TaskCreate(
            title=choice.title or suggestion.title[:200],
            task_type=choice.task_type,
            course_id=choice.course_id,
            deadline_at=suggestion.due_at,
            estimated_minutes=choice.estimated_minutes,
            priority=choice.priority,
        ),
    )
    suggestion.status = SuggestionStatus.ACCEPTED
    suggestion.task_id = task.id
    db.commit()
    return task.id


def dismiss_suggestion(db: Session, user: User, suggestion_id: uuid.UUID) -> None:
    _pending(db, user, suggestion_id).status = SuggestionStatus.DISMISSED
    db.commit()


def list_busy(db: Session, user: User, start: datetime, end: datetime) -> list[BusyRead]:
    """Every busy time in a range, from weekly commitments, one-off ones and connected calendars."""
    if end <= start or end - start > _MAX_BUSY_RANGE:
        raise InvalidFieldsError({"end": "Choose a range of up to 62 days."})
    zone = ZoneInfo(user.timezone)
    result: list[BusyRead] = []
    for block in db.scalars(select(RecurringBlock).where(RecurringBlock.user_id == user.id)):
        rule = WeeklyTime(block.day_of_week, block.start_minute, block.end_minute)
        result.extend(
            BusyRead(
                source="weekly",
                id=block.id,
                title=block.title,
                category=block.category,
                start_at=occurrence.start,
                end_at=occurrence.end,
                feed_name=None,
            )
            for occurrence in expand_rules((rule,), start, end, zone)
            if occurrence.end > start and occurrence.start < end
        )
    rows = db.execute(
        select(OneOffBlock, CalendarFeed.name)
        .outerjoin(CalendarFeed, OneOffBlock.feed_id == CalendarFeed.id)
        .where(
            OneOffBlock.user_id == user.id,
            OneOffBlock.end_at > start,
            OneOffBlock.start_at < end,
        )
    ).all()
    result.extend(
        BusyRead(
            source="once" if block.feed_id is None else "calendar",
            id=block.id,
            title=block.title,
            category=block.category,
            start_at=block.start_at,
            end_at=block.end_at,
            feed_name=feed_name,
        )
        for block, feed_name in rows
    )
    return sorted(result, key=lambda item: (item.start_at, item.title))

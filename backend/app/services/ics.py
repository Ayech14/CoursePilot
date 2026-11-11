"""Reads an iCalendar file into busy times and deadlines. No database, no network.

- A timed event is busy time.
- An event with no length, which is how Moodle and many course sites publish "is due" items, is a
  deadline.
- All-day events are skipped: in school calendars they are mostly holidays and notes, and
  blocking whole days for them would empty the schedule.
- Cancelled events, and events marked "free" (transparent), are skipped.
- A time with no zone ("floating") is read in the student's zone.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events  # type: ignore[import-untyped]

MAX_BUSY = 3000
MAX_DEADLINES = 500
_DEADLINE_LENGTH = timedelta(minutes=1)


class IcsError(Exception):
    pass


@dataclass(frozen=True)
class BusyEvent:
    uid: str
    title: str
    start: datetime
    end: datetime


@dataclass(frozen=True)
class DeadlineEvent:
    uid: str
    title: str
    due: datetime
    hints: tuple[str, ...]


@dataclass
class ParsedCalendar:
    busy: list[BusyEvent] = field(default_factory=list)
    deadlines: list[DeadlineEvent] = field(default_factory=list)
    skipped_all_day: int = 0


def _aware(value: datetime, zone: ZoneInfo) -> datetime:
    return value.replace(tzinfo=zone, fold=0) if value.tzinfo is None else value


def _text(event: Any, name: str) -> str:
    value = event.get(name)
    return "" if value is None else str(value).strip()


def _categories(event: Any) -> tuple[str, ...]:
    raw = event.get("CATEGORIES")
    if raw is None:
        return ()
    values = raw if isinstance(raw, list) else [raw]
    return tuple(str(cat) for item in values for cat in getattr(item, "cats", [item]))


def _end_of(event: Any, start: datetime, zone: ZoneInfo) -> datetime:
    if event.get("DTEND") is not None:
        end = event.decoded("DTEND")
        if isinstance(end, datetime):
            return _aware(end, zone)
    if event.get("DURATION") is not None:
        duration: timedelta = event.decoded("DURATION")
        return start + duration
    return start


def parse(data: bytes, zone: ZoneInfo, start: datetime, end: datetime) -> ParsedCalendar:
    try:
        calendar = icalendar.Calendar.from_ical(data)
        events = recurring_ical_events.of(calendar, skip_bad_series=True).between(start, end)
    except Exception as exc:  # The libraries raise many types for malformed input.
        raise IcsError("That link did not return a calendar file we can read.") from exc

    result = ParsedCalendar()
    for event in events:
        if _text(event, "STATUS").upper() == "CANCELLED":
            continue
        if _text(event, "TRANSP").upper() == "TRANSPARENT":
            continue
        raw_start = event.decoded("DTSTART")
        if isinstance(raw_start, date) and not isinstance(raw_start, datetime):
            result.skipped_all_day += 1
            continue
        event_start = _aware(raw_start, zone)
        event_end = _end_of(event, event_start, zone)
        uid = _text(event, "UID") or _text(event, "SUMMARY")
        key = f"{uid}|{event_start.astimezone(UTC).isoformat()}"[:500]
        title = _text(event, "SUMMARY")

        if event_end - event_start <= _DEADLINE_LENGTH:
            if len(result.deadlines) < MAX_DEADLINES:
                result.deadlines.append(
                    DeadlineEvent(key, (title or "Deadline")[:200], event_start, _categories(event))
                )
        elif len(result.busy) < MAX_BUSY:
            result.busy.append(BusyEvent(key, (title or "Busy")[:120], event_start, event_end))
    return result

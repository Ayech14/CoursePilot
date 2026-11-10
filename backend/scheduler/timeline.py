"""Turns availability into concrete study slots.

Weekly rules are local wall-clock values, so they are expanded one local date at a time. After
that, every calculation uses UTC instants, which makes 23- and 25-hour days a non-issue.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

from scheduler.models import Interval, PlanRequest, SessionClass, WeeklyTime

_SNAP_MINUTES = 5
_MINUTES_PER_DAY = 1440


@dataclass(frozen=True)
class Slot:
    """A place a session could go. Times are whole minutes after the timeline's origin."""

    start: int
    end: int
    day: int

    @property
    def minutes(self) -> int:
        return self.end - self.start


@dataclass(frozen=True)
class Timeline:
    origin: datetime
    first_day: date
    slots: tuple[Slot, ...]
    day_budgets: tuple[int, ...]

    def to_minutes(self, instant: datetime) -> int:
        return int((instant - self.origin).total_seconds() // 60)

    def to_instant(self, minutes: int) -> datetime:
        return self.origin + timedelta(minutes=minutes)


def round_up_to_snap(instant: datetime) -> datetime:
    """The next five-minute mark, so that sessions start at sensible times."""
    utc = instant.astimezone(UTC)
    past_mark = timedelta(
        minutes=utc.minute % _SNAP_MINUTES, seconds=utc.second, microseconds=utc.microsecond
    )
    return utc if not past_mark else utc + timedelta(minutes=_SNAP_MINUTES) - past_mark


def local_to_utc(day: date, minute: int, zone: ZoneInfo) -> datetime:
    """The instant a local date and time refers to.

    When clocks go back a time happens twice, and this uses the first occurrence. When clocks go
    forward a time may not exist, and this uses the first valid instant after the gap.
    """
    if minute >= _MINUTES_PER_DAY:
        return local_to_utc(day + timedelta(days=1), minute - _MINUTES_PER_DAY, zone)

    naive = datetime(day.year, day.month, day.day, minute // 60, minute % 60)
    instant = naive.replace(tzinfo=zone, fold=0).astimezone(UTC)
    if instant.astimezone(zone).replace(tzinfo=None) == naive:
        return instant
    return _end_of_gap(naive, zone)


def _end_of_gap(naive: datetime, zone: ZoneInfo) -> datetime:
    # Inside a gap fold=1 gives an instant before the transition and fold=0 one after it.
    before = naive.replace(tzinfo=zone, fold=1).astimezone(UTC)
    after = naive.replace(tzinfo=zone, fold=0).astimezone(UTC)
    new_offset = after.astimezone(zone).utcoffset()
    while after - before > timedelta(minutes=1):
        middle = before + timedelta(minutes=((after - before).total_seconds() // 120))
        if middle.astimezone(zone).utcoffset() == new_offset:
            after = middle
        else:
            before = middle
    return after


def merge_intervals(intervals: Iterable[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for item in sorted(intervals, key=lambda i: (i.start, i.end)):
        if item.start >= item.end:
            continue
        if merged and item.start <= merged[-1].end:
            merged[-1] = Interval(merged[-1].start, max(merged[-1].end, item.end))
        else:
            merged.append(item)
    return merged


def subtract_intervals(free: list[Interval], cuts: list[Interval]) -> list[Interval]:
    """Remove `cuts` from `free`. Both lists must be sorted and non-overlapping."""
    result: list[Interval] = []
    for item in free:
        cursor = item.start
        for cut in cuts:
            if cut.end <= cursor:
                continue
            if cut.start >= item.end:
                break
            if cut.start > cursor:
                result.append(Interval(cursor, cut.start))
            cursor = max(cursor, cut.end)
        if cursor < item.end:
            result.append(Interval(cursor, item.end))
    return result


def _expand_for_day(rules: tuple[WeeklyTime, ...], day: date, zone: ZoneInfo) -> list[Interval]:
    weekday = day.weekday()
    return merge_intervals(
        Interval(
            local_to_utc(day, rule.start_minute, zone), local_to_utc(day, rule.end_minute, zone)
        )
        for rule in rules
        if rule.day_of_week == weekday
    )


def expand_rules(
    rules: tuple[WeeklyTime, ...], start: datetime, end: datetime, zone: ZoneInfo
) -> list[Interval]:
    """Every occurrence of weekly rules in a range, as merged real instants."""
    first = start.astimezone(zone).date() - timedelta(days=1)
    last = end.astimezone(zone).date() + timedelta(days=1)
    occurrences: list[Interval] = []
    for offset in range((last - first).days + 1):
        occurrences.extend(_expand_for_day(rules, first + timedelta(days=offset), zone))
    return merge_intervals(occurrences)


def pinned_sessions(request: PlanRequest) -> list[Interval]:
    return [
        Interval(session.start, session.end)
        for session in request.existing_sessions
        if session.session_class is not SessionClass.FLEXIBLE
    ]


def build_timeline(request: PlanRequest) -> Timeline:
    zone = ZoneInfo(request.timezone)
    preferences = request.preferences
    origin = round_up_to_snap(request.now)
    horizon = request.horizon_end.astimezone(UTC)
    first_day = origin.astimezone(zone).date()
    last_day = horizon.astimezone(zone).date()
    day_count = max((last_day - first_day).days + 1, 0)

    pinned = pinned_sessions(request)
    margin = timedelta(minutes=preferences.break_minutes)
    cuts = merge_intervals(
        [*request.one_off_blocks, *(Interval(p.start - margin, p.end + margin) for p in pinned)]
    )

    budgets = [preferences.max_daily_minutes] * day_count
    for session in pinned:
        index = (session.start.astimezone(zone).date() - first_day).days
        if 0 <= index < day_count:
            minutes = int((session.end - session.start).total_seconds() // 60)
            budgets[index] = max(budgets[index] - minutes, 0)

    today = (request.now.astimezone(zone).date() - first_day).days
    if 0 <= today < day_count:
        budgets[today] = max(budgets[today] - request.studied_today_minutes, 0)

    preferred = timedelta(minutes=preferences.preferred_session_minutes)
    minimum = timedelta(minutes=preferences.min_session_minutes)

    slots: list[Slot] = []
    earliest = origin  # Moves past each slot, so that breaks also hold across local midnight.
    for index in range(day_count):
        day = first_day + timedelta(days=index)
        free = _expand_for_day(request.windows, day, zone)
        free = subtract_intervals(free, _expand_for_day(request.weekly_blocks, day, zone))
        free = subtract_intervals(free, cuts)
        for item in free:
            end_limit = min(item.end, horizon)
            start = max(item.start, earliest)
            while end_limit - start >= minimum:
                end = min(start + preferred, end_limit)
                slots.append(_as_slot(start, end, index, origin))
                earliest = end + margin
                start = earliest

    return Timeline(origin, first_day, tuple(slots), tuple(budgets))


def _as_slot(start: datetime, end: datetime, day: int, origin: datetime) -> Slot:
    return Slot(
        int((start - origin).total_seconds() // 60), int((end - origin).total_seconds() // 60), day
    )

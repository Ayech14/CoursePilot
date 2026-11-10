"""Checking a time the student picked by hand, and suggesting better ones.

Overlap is impossible, so it is refused. Everything else is the student's call, so it is only a
warning: they know their own life better than the rules do.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from zoneinfo import ZoneInfo

from scheduler.models import ExistingSession, Interval, PlanRequest, TaskInput
from scheduler.timeline import (
    expand_rules,
    merge_intervals,
    round_up_to_snap,
    subtract_intervals,
)


class ConflictKind(StrEnum):
    OVERLAP = "overlap"
    IN_PAST = "in_past"


class WarningKind(StrEnum):
    OUTSIDE_AVAILABILITY = "outside_availability"
    IN_BLOCK = "in_block"
    NO_BREAK = "no_break"
    DAILY_LIMIT = "daily_limit"
    PAST_DEADLINE = "past_deadline"


@dataclass(frozen=True)
class Conflict:
    kind: ConflictKind
    session_id: str | None = None


@dataclass(frozen=True)
class PlacementCheck:
    conflicts: tuple[Conflict, ...]
    warnings: tuple[WarningKind, ...]

    @property
    def ok(self) -> bool:
        return not self.conflicts and not self.warnings


def _others(request: PlanRequest, ignoring: str | None) -> list[ExistingSession]:
    return [s for s in request.existing_sessions if s.id != ignoring]


def _minutes(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() // 60)


def _task(request: PlanRequest, task_id: str) -> TaskInput | None:
    return next((task for task in request.tasks if task.id == task_id), None)


def _span_end(request: PlanRequest, end: datetime) -> datetime:
    return max(end, request.horizon_end) + timedelta(days=1)


def check_placement(
    request: PlanRequest,
    task_id: str,
    start: datetime,
    end: datetime,
    ignoring: str | None = None,
) -> PlacementCheck:
    zone = ZoneInfo(request.timezone)
    others = _others(request, ignoring)

    conflicts: list[Conflict] = []
    if start < request.now:
        conflicts.append(Conflict(ConflictKind.IN_PAST))
    conflicts.extend(
        Conflict(ConflictKind.OVERLAP, s.id) for s in others if start < s.end and s.start < end
    )

    warnings: list[WarningKind] = []
    span_end = _span_end(request, end)
    windows = expand_rules(request.windows, min(start, request.now), span_end, zone)
    if not any(w.start <= start and end <= w.end for w in windows):
        warnings.append(WarningKind.OUTSIDE_AVAILABILITY)

    blocks = [
        *expand_rules(request.weekly_blocks, min(start, request.now), span_end, zone),
        *request.one_off_blocks,
    ]
    if any(start < b.end and b.start < end for b in blocks):
        warnings.append(WarningKind.IN_BLOCK)

    margin = timedelta(minutes=request.preferences.break_minutes)
    touching = any(
        start < s.end + margin and s.start - margin < end
        for s in others
        if not (start < s.end and s.start < end)
    )
    if touching:
        warnings.append(WarningKind.NO_BREAK)

    day = start.astimezone(zone).date()
    day_total = _minutes(start, end) + sum(
        _minutes(s.start, s.end) for s in others if s.start.astimezone(zone).date() == day
    )
    if day == request.now.astimezone(zone).date():
        day_total += request.studied_today_minutes
    if day_total > request.preferences.max_daily_minutes:
        warnings.append(WarningKind.DAILY_LIMIT)

    task = _task(request, task_id)
    if task is not None and task.deadline is not None and end > task.deadline:
        warnings.append(WarningKind.PAST_DEADLINE)

    return PlacementCheck(tuple(conflicts), tuple(warnings))


def _snap_up_inside(candidate: datetime, latest_start: datetime) -> datetime | None:
    snapped = round_up_to_snap(candidate)
    return snapped if snapped <= latest_start else None


def suggest_slots(
    request: PlanRequest,
    task_id: str,
    minutes: int,
    near: datetime,
    ignoring: str | None = None,
    limit: int = 5,
) -> tuple[Interval, ...]:
    """Valid times of the same length, closest first, preferring the requested day."""
    zone = ZoneInfo(request.timezone)
    preferences = request.preferences
    duration = timedelta(minutes=minutes)
    margin = timedelta(minutes=preferences.break_minutes)
    others = _others(request, ignoring)
    task = _task(request, task_id)

    earliest = round_up_to_snap(request.now)
    free = expand_rules(request.windows, earliest, request.horizon_end, zone)
    cuts = merge_intervals(
        [
            *expand_rules(request.weekly_blocks, earliest, request.horizon_end, zone),
            *request.one_off_blocks,
            *(Interval(s.start - margin, s.end + margin) for s in others),
        ]
    )

    day_minutes: dict[object, int] = {
        request.now.astimezone(zone).date(): request.studied_today_minutes
    }
    for session in others:
        day = session.start.astimezone(zone).date()
        day_minutes[day] = day_minutes.get(day, 0) + _minutes(session.start, session.end)

    target_day = near.astimezone(zone).date()
    candidates: list[tuple[bool, float, datetime]] = []
    for item in subtract_intervals(free, cuts):
        first = max(item.start, earliest)
        last_end = min(item.end, request.horizon_end)
        if task is not None and task.deadline is not None:
            last_end = min(last_end, task.deadline)
        latest_start = last_end - duration
        if latest_start < first:
            continue
        start = _snap_up_inside(max(first, min(near, latest_start)), latest_start)
        if start is None:
            continue
        day = start.astimezone(zone).date()
        if day_minutes.get(day, 0) + minutes > preferences.max_daily_minutes:
            continue
        distance = abs((start - near).total_seconds())
        candidates.append((day != target_day, distance, start))

    candidates.sort()
    return tuple(Interval(start, start + duration) for _, _, start in candidates[:limit])

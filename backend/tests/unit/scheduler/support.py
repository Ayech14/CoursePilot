"""Scenario builders and an invariant checker written independently of the engine.

The checker works from wall-clock rules and never calls engine code, so a bug in the engine's
time handling cannot hide by agreeing with itself.
"""

import random
from collections import defaultdict
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from scheduler.models import (
    ExistingSession,
    Interval,
    PlanRequest,
    PlanResult,
    Preferences,
    SessionClass,
    TaskInput,
    WeeklyTime,
)

PREFS = Preferences(
    preferred_session_minutes=50,
    min_session_minutes=25,
    break_minutes=10,
    max_daily_minutes=360,
    deadline_buffer_hours=0,
)

# A Monday, in a week with no daylight saving change in the zones used by hand-written tests.
MONDAY = datetime(2026, 2, 2, 8, 0, tzinfo=UTC)


def every_day(start: int = 540, end: int = 1020) -> tuple[WeeklyTime, ...]:
    return tuple(WeeklyTime(day, start, end) for day in range(7))


def task(
    task_id: str = "a",
    minutes: int = 100,
    *,
    due_days: float | None = 7,
    priority: int = 2,
    course: str | None = "c1",
    now: datetime = MONDAY,
) -> TaskInput:
    deadline = None if due_days is None else now + timedelta(days=due_days)
    return TaskInput(task_id, minutes, priority, deadline, course)


def request(*tasks: TaskInput, **overrides: Any) -> PlanRequest:
    values: dict[str, Any] = {
        "now": MONDAY,
        "timezone": "UTC",
        "horizon_end": MONDAY + timedelta(days=28),
        "tasks": tasks,
        "windows": every_day(),
        "preferences": PREFS,
    }
    return PlanRequest(**(values | overrides))


def minutes_of(start: datetime, end: datetime) -> int:
    return int((end - start).total_seconds() // 60)


def _wall_minute(local: datetime) -> int:
    return local.hour * 60 + local.minute


def _end_wall_minute(local_end: datetime) -> int:
    """Measured from the session's last minute, so that midnight and clock jumps read correctly."""
    last_minute = (local_end.astimezone(UTC) - timedelta(minutes=1)).astimezone(local_end.tzinfo)
    return _wall_minute(last_minute) + 1


def _inside(rule: WeeklyTime, local_start: datetime, local_end: datetime) -> bool:
    """Whether a session sits inside a weekly rule, comparing wall-clock values."""
    if local_start.weekday() != rule.day_of_week:
        return False
    start = _wall_minute(local_start)
    end = _end_wall_minute(local_end)
    # During a repeated hour the wall clock runs backwards, so the lower bound cannot be judged.
    return (local_start.fold == 1 or start >= rule.start_minute) and end <= rule.end_minute


def _touches(rule: WeeklyTime, local_start: datetime, local_end: datetime) -> bool:
    if local_start.weekday() != rule.day_of_week or local_start.fold == 1:
        return False
    start = _wall_minute(local_start)
    end = _end_wall_minute(local_end)
    return start < rule.end_minute and end > rule.start_minute


def _joined(rules: tuple[WeeklyTime, ...]) -> list[WeeklyTime]:
    """Touching weekly ranges form one continuous stretch of free time."""
    joined: list[WeeklyTime] = []
    for rule in sorted(rules, key=lambda r: (r.day_of_week, r.start_minute)):
        last = joined[-1] if joined else None
        if last and last.day_of_week == rule.day_of_week and rule.start_minute <= last.end_minute:
            joined[-1] = WeeklyTime(
                last.day_of_week, last.start_minute, max(last.end_minute, rule.end_minute)
            )
        else:
            joined.append(rule)
    return joined


def _pinned(req: PlanRequest) -> list[ExistingSession]:
    return [s for s in req.existing_sessions if s.session_class is not SessionClass.FLEXIBLE]


def assert_invariants(req: PlanRequest, result: PlanResult) -> None:
    zone = ZoneInfo(req.timezone)
    prefs = req.preferences
    tasks = {t.id: t for t in req.tasks}
    pinned = _pinned(req)
    automatic = sorted(result.placements, key=lambda p: p.start)
    windows = _joined(req.windows)

    everything = sorted([(p.start, p.end) for p in automatic] + [(s.start, s.end) for s in pinned])
    for (_, first_end), (second_start, _) in zip(everything, everything[1:], strict=False):
        assert first_end <= second_start, "sessions overlap"

    for first, second in zip(automatic, automatic[1:], strict=False):
        assert second.start - first.end >= timedelta(minutes=prefs.break_minutes), "no break"

    placed_by_task: dict[str, int] = defaultdict(int)
    minutes_by_day: dict[date, int] = defaultdict(int)
    for session in pinned:
        minutes_by_day[session.start.astimezone(zone).date()] += minutes_of(
            session.start, session.end
        )

    for placement in automatic:
        assert placement.start >= req.now, "scheduled in the past"
        assert placement.end <= req.horizon_end, "beyond the horizon"
        assert placement.start < placement.end
        assert placement.minutes <= prefs.preferred_session_minutes, "too long"

        local_start = placement.start.astimezone(zone)
        local_end = placement.end.astimezone(zone)
        assert any(_inside(w, local_start, local_end) for w in windows), (
            f"outside availability: {local_start} to {local_end}"
        )
        assert not any(_touches(b, local_start, local_end) for b in req.weekly_blocks), (
            f"in a weekly block: {local_start}"
        )
        for block in req.one_off_blocks:
            assert placement.end <= block.start or placement.start >= block.end, "in a block"
        for session in pinned:
            margin = timedelta(minutes=prefs.break_minutes)
            assert (
                placement.end + margin <= session.start or placement.start >= session.end + margin
            ), "no break around a kept session"

        source = tasks[placement.task_id]
        if source.deadline is not None:
            assert placement.end <= source.deadline, "after the deadline"
        placed_by_task[placement.task_id] += placement.minutes
        minutes_by_day[local_start.date()] += placement.minutes

    placed_days = {p.start.astimezone(zone).date() for p in automatic}
    for day in placed_days:
        assert minutes_by_day[day] <= prefs.max_daily_minutes, f"daily limit exceeded on {day}"

    pinned_by_task: dict[str, int] = defaultdict(int)
    for session in pinned:
        pinned_by_task[session.task_id] += minutes_of(session.start, session.end)
    for task_id, placed in placed_by_task.items():
        assert placed + pinned_by_task[task_id] <= tasks[task_id].remaining_minutes, "over-planned"

    # Accounting: all demand is placed or reported, and nothing is double counted.
    reported = {r.task_id: r.shortfall_minutes for r in result.at_risk}
    reported |= {u.task_id: u.minutes for u in result.unplaced}
    for source in req.tasks:
        demand = max(source.remaining_minutes - pinned_by_task[source.id], 0)
        assert placed_by_task[source.id] + reported.get(source.id, 0) == demand, (
            f"minutes unaccounted for on {source.id}"
        )


ZONES = (
    "UTC",
    "America/Toronto",
    "America/St_Johns",
    "America/Havana",  # Clocks change at midnight, so whole-day edges move.
    "Europe/London",
    "Asia/Tehran",
    "Asia/Kolkata",
    "Australia/Lord_Howe",  # A 30-minute daylight saving shift.
)

# Starting points shortly before daylight saving changes, plus an ordinary week.
START_INSTANTS = (
    datetime(2026, 3, 5, 15, 7, tzinfo=UTC),  # Before North America springs forward.
    datetime(2026, 10, 29, 3, 2, tzinfo=UTC),  # Before North America falls back.
    datetime(2026, 3, 26, 22, 0, tzinfo=UTC),  # Before Europe springs forward.
    datetime(2026, 10, 1, 9, 33, tzinfo=UTC),  # Before Lord Howe changes.
    datetime(2026, 6, 10, 12, 0, tzinfo=UTC),
)


def random_request(seed: int) -> PlanRequest:
    rng = random.Random(seed)  # noqa: S311  # Reproducible test data, not security.
    now = rng.choice(START_INSTANTS) + timedelta(minutes=rng.randrange(0, 1440))
    preferred = rng.choice((25, 30, 45, 50, 60, 90))
    prefs = Preferences(
        preferred_session_minutes=preferred,
        min_session_minutes=rng.choice((5, 10, min(preferred, 25))),
        break_minutes=rng.choice((0, 5, 10, 15)),
        max_daily_minutes=rng.choice((60, 120, 240, 360, 600)),
        deadline_buffer_hours=rng.choice((0, 0, 12, 24)),
    )

    windows: list[WeeklyTime] = []
    for day in range(7):
        cursor = rng.choice((0, 60, 120, 480, 540))
        for _ in range(rng.randint(0, 3)):
            start = cursor + rng.randrange(0, 240, 15)
            end = start + rng.randrange(30, 480, 15)
            if end > 1440:
                break
            windows.append(WeeklyTime(day, start, end))
            cursor = end

    weekly_blocks = tuple(
        WeeklyTime(
            rng.randrange(7), (s := rng.randrange(0, 1300, 15)), s + rng.randrange(30, 140, 5)
        )
        for _ in range(rng.randint(0, 4))
    )
    horizon_days = rng.choice((7, 14, 28))
    one_off = tuple(
        Interval(
            (b := now + timedelta(minutes=rng.randrange(0, horizon_days * 1440))),
            b + timedelta(minutes=rng.randrange(30, 2880)),
        )
        for _ in range(rng.randint(0, 3))
    )

    courses = ("c1", "c2", "c3", None)
    tasks = tuple(
        TaskInput(
            id=f"t{index}",
            remaining_minutes=rng.randrange(5, 900, 5),
            priority=rng.randint(1, 4),
            deadline=(
                None
                if rng.random() < 0.15
                else now + timedelta(minutes=rng.randrange(-600, (horizon_days + 7) * 1440))
            ),
            course_id=rng.choice(courses),
        )
        for index in range(rng.randint(0, 14))
    )

    # Kept sessions on a coarse grid, spaced so that they cannot overlap one another.
    existing: list[ExistingSession] = []
    if tasks:
        start = now + timedelta(hours=1)
        for index in range(rng.randint(0, 5)):
            start += timedelta(minutes=rng.randrange(300, 3000, 15))
            length = timedelta(minutes=rng.randrange(15, 90, 5))
            existing.append(
                ExistingSession(
                    f"s{index}",
                    rng.choice(tasks).id,
                    start,
                    start + length,
                    rng.choice(list(SessionClass)),
                )
            )
            start += length

    return PlanRequest(
        now=now,
        timezone=rng.choice(ZONES),
        horizon_end=now + timedelta(days=horizon_days),
        tasks=tasks,
        windows=tuple(windows),
        preferences=prefs,
        weekly_blocks=weekly_blocks,
        one_off_blocks=one_off,
        existing_sessions=tuple(existing),
    )


def shuffled(req: PlanRequest, seed: int) -> PlanRequest:
    rng = random.Random(seed)  # noqa: S311
    tasks = list(req.tasks)
    rng.shuffle(tasks)
    windows = list(req.windows)
    rng.shuffle(windows)
    return replace(req, tasks=tuple(tasks), windows=tuple(windows))

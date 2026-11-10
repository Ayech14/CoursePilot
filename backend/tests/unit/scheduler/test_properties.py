"""Invariants checked on hundreds of generated scenarios, reproducible by seed.

Scenarios mix time zones, daylight saving changes, kept sessions, blocks, overload and odd
preference combinations. If one fails, the seed in the test name reproduces it exactly.
"""

import time
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from scheduler import plan
from scheduler.models import (
    ExistingSession,
    PlanRequest,
    Preferences,
    SessionClass,
    TaskInput,
    WeeklyTime,
)
from scheduler.planner import plain_edf_late_minutes
from scheduler.repair import repair
from tests.unit.scheduler.support import assert_invariants, random_request, shuffled

SEEDS = range(500)


@pytest.mark.parametrize("seed", SEEDS)
def test_invariants_hold(seed: int) -> None:
    request = random_request(seed)
    assert_invariants(request, plan(request))


@pytest.mark.parametrize("seed", SEEDS)
def test_results_are_deterministic(seed: int) -> None:
    request = random_request(seed)
    first = plan(request)
    assert repr(plan(request)) == repr(first)
    assert repr(plan(shuffled(request, seed))) == repr(first)


@pytest.mark.parametrize("seed", SEEDS)
def test_if_plain_edf_meets_every_deadline_so_does_the_plan(seed: int) -> None:
    request = random_request(seed)
    if plain_edf_late_minutes(request) == 0:
        result = plan(request)
        assert [r for r in result.at_risk if r.reason == "insufficient_time"] == []


def test_generated_scenarios_exercise_both_outcomes() -> None:
    """Guards the test above against passing because no scenario was relevant."""
    results = [plain_edf_late_minutes(random_request(seed)) for seed in SEEDS]
    assert sum(1 for late in results if late == 0) > 50
    assert sum(1 for late in results if late > 0) > 50


def _heavy_semester(horizon_days: int) -> PlanRequest:
    now = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)
    tasks = tuple(
        TaskInput(
            id=f"t{index:03}",
            remaining_minutes=120 + (index * 37) % 400,
            priority=1 + index % 4,
            deadline=now + timedelta(hours=30 + (index * 53) % (horizon_days * 24 - 30)),
            course_id=f"c{index % 6}",
        )
        for index in range(60)
    )
    return PlanRequest(
        now=now,
        timezone="America/Toronto",
        horizon_end=now + timedelta(days=horizon_days),
        tasks=tasks,
        windows=tuple(WeeklyTime(day, 480, 1320) for day in range(7)),
        preferences=Preferences(50, 25, 10, 480, 12),
    )


@pytest.mark.parametrize(
    ("horizon_days", "limit_seconds"),
    [(28, 2.0), (120, 10.0)],
)
def test_planning_time_stays_interactive(horizon_days: int, limit_seconds: float) -> None:
    request = _heavy_semester(horizon_days)
    started = time.perf_counter()
    result = plan(request)
    elapsed = time.perf_counter() - started
    print(f"\nplanned {len(request.tasks)} tasks over {horizon_days} days in {elapsed:.3f}s")
    assert_invariants(request, result)
    assert elapsed < limit_seconds


def test_repair_stays_interactive_under_a_full_schedule() -> None:
    fresh = _heavy_semester(28)
    sessions = tuple(
        ExistingSession(f"s{i}", p.task_id, p.start, p.end, SessionClass.FLEXIBLE)
        for i, p in enumerate(plan(fresh).placements)
    )
    # A far-reaching change: a whole weekday of availability disappears.
    windows = tuple(w for w in fresh.windows if w.day_of_week != 2)
    request = replace(fresh, windows=windows, existing_sessions=sessions)
    started = time.perf_counter()
    result = repair(request)
    elapsed = time.perf_counter() - started
    print(f"\nrepaired {len(sessions)} sessions in {elapsed:.3f}s, {len(result.changes)} changes")
    assert result.changes
    assert elapsed < 5.0


def test_scales_with_a_tight_workload() -> None:
    request = replace(_heavy_semester(28), preferences=Preferences(50, 25, 10, 240, 0))
    started = time.perf_counter()
    result = plan(request)
    print(
        f"\noverloaded plan in {time.perf_counter() - started:.3f}s, {len(result.at_risk)} at risk"
    )
    assert_invariants(request, result)

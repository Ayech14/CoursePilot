from collections import Counter
from dataclasses import replace
from datetime import timedelta

import pytest

from scheduler import plan
from scheduler.explain import describe, describe_risk
from scheduler.models import (
    ExistingSession,
    PlanResult,
    Reason,
    RiskReason,
    SessionClass,
    TaskInput,
    WeeklyTime,
)
from scheduler.planner import usable_minutes
from tests.unit.scheduler.support import MONDAY, PREFS, assert_invariants, every_day, request, task


def run(*tasks: TaskInput, **overrides: object) -> PlanResult:
    req = request(*tasks, **overrides)
    result = plan(req)
    assert_invariants(req, result)
    return result


def minutes_for(result: PlanResult, task_id: str) -> int:
    return sum(p.minutes for p in result.placements if p.task_id == task_id)


def sessions_per_day(result: PlanResult) -> Counter[str]:
    return Counter(p.start.date().isoformat() for p in result.placements)


# --- Session sizing -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("remaining", "capacity", "expected"),
    [
        (30, 50, 30),  # Finishes the task.
        (10, 50, 10),  # A task's last bit of work may be short.
        (200, 50, 50),
        (55, 50, 30),  # Would leave 5; leaves the minimum of 25 instead.
        (75, 50, 50),  # Leaves exactly the minimum.
        (200, 20, 0),  # The gap is too short to start.
        (40, 30, 30),  # Cannot leave 25 without going under 25 here, so it keeps its size.
    ],
)
def test_usable_minutes(remaining: int, capacity: int, expected: int) -> None:
    assert usable_minutes(remaining, capacity, 25) == expected


def test_work_splits_without_a_tiny_final_session() -> None:
    result = run(task(minutes=105, due_days=7))
    assert sorted(p.minutes for p in result.placements) == [25, 30, 50]


def test_exact_work_is_placed() -> None:
    assert minutes_for(run(task(minutes=240)), "a") == 240


# --- Basic constraints ----------------------------------------------------------------------


def test_nothing_to_do_gives_empty_plan() -> None:
    assert run() == PlanResult(placements=())


def test_task_with_zero_remaining_is_ignored() -> None:
    assert run(task(minutes=0)).placements == ()


def test_daily_limit_holds_under_pressure() -> None:
    prefs = replace(PREFS, max_daily_minutes=100)
    result = run(task(minutes=800, due_days=5), preferences=prefs)
    assert (
        max(
            sum(p.minutes for p in result.placements if p.start.date() == d)
            for d in {p.start.date() for p in result.placements}
        )
        <= 100
    )


def test_session_never_crosses_the_deadline() -> None:
    # Due at 09:30 on the first day, with a slot from 09:00 to 09:50.
    result = run(task(minutes=30, due_days=1.5 / 24), windows=every_day())
    assert [p.minutes for p in result.placements] == [30]


def test_kept_minutes_reduce_what_is_planned() -> None:
    kept = ExistingSession(
        "s", "a", MONDAY + timedelta(hours=1), MONDAY + timedelta(hours=2), SessionClass.LOCKED
    )
    assert minutes_for(run(task(minutes=100), existing_sessions=(kept,)), "a") == 40


def test_flexible_minutes_do_not_reduce_what_is_planned() -> None:
    flexible = ExistingSession(
        "s", "a", MONDAY + timedelta(hours=1), MONDAY + timedelta(hours=2), SessionClass.FLEXIBLE
    )
    assert minutes_for(run(task(minutes=100), existing_sessions=(flexible,)), "a") == 100


def test_fully_covered_task_needs_nothing_new() -> None:
    kept = ExistingSession(
        "s", "a", MONDAY + timedelta(hours=1), MONDAY + timedelta(hours=3), SessionClass.STICKY
    )
    assert run(task(minutes=100), existing_sessions=(kept,)).placements == ()


# --- Prioritization -------------------------------------------------------------------------


def test_more_urgent_task_goes_first() -> None:
    result = run(task("later", 50, due_days=20), task("soon", 50, due_days=2))
    assert result.placements[0].task_id == "soon"


def test_higher_priority_breaks_a_tie_in_urgency() -> None:
    result = run(task("low", 50, priority=1), task("high", 50, priority=4))
    assert result.placements[0].task_id == "high"


def test_courses_are_balanced() -> None:
    one = [task(f"a{i}", 50, due_days=14, course="alg") for i in range(4)]
    two = [task(f"b{i}", 50, due_days=14, course="art") for i in range(4)]
    result = run(*one, *two, preferences=replace(PREFS, max_daily_minutes=200))
    first_four = [p.task_id[0] for p in result.placements[:4]]
    assert Counter(first_four) == {"a": 2, "b": 2}


def test_work_is_spread_rather_than_crammed() -> None:
    result = run(task(minutes=600, due_days=14))
    per_day = sessions_per_day(result)
    assert len(per_day) >= 8
    assert max(per_day.values()) <= 2


def test_light_load_leaves_most_of_the_day_free() -> None:
    result = run(task(minutes=100, due_days=10))
    assert max(sessions_per_day(result).values()) == 1


def test_deadline_pressure_fills_the_day_despite_pacing() -> None:
    result = run(task(minutes=300, due_days=1))
    assert minutes_for(result, "a") == 300
    assert len(sessions_per_day(result)) == 1


# --- Deadlines, buffers, overload -----------------------------------------------------------


def test_buffer_finishes_work_early_when_possible() -> None:
    prefs = replace(PREFS, deadline_buffer_hours=48)
    result = run(task(minutes=200, due_days=7), preferences=prefs)
    assert max(p.end for p in result.placements) <= MONDAY + timedelta(days=5)


def test_buffer_is_dropped_when_it_cannot_be_met() -> None:
    prefs = replace(PREFS, deadline_buffer_hours=48)
    result = run(task(minutes=1000, due_days=3), preferences=prefs)
    assert result.at_risk == ()
    assert minutes_for(result, "a") == 1000


def test_an_impossible_task_does_not_cost_other_tasks_their_margin() -> None:
    prefs = replace(PREFS, deadline_buffer_hours=48)
    result = run(
        task("hopeless", 900, due_days=0.05, priority=1),
        task("normal", 200, due_days=7),
        preferences=prefs,
    )
    assert [r.task_id for r in result.at_risk] == ["hopeless"]
    normal = [p for p in result.placements if p.task_id == "normal"]
    assert max(p.end for p in normal) <= MONDAY + timedelta(days=5)


def test_overload_reports_the_exact_shortfall() -> None:
    windows = (WeeklyTime(0, 540, 650),)  # Two sessions fit on Monday.
    result = run(task(minutes=300, due_days=1), windows=windows)
    assert minutes_for(result, "a") == 100
    assert [(r.task_id, r.shortfall_minutes, r.reason) for r in result.at_risk] == [
        ("a", 200, RiskReason.INSUFFICIENT_TIME)
    ]


def test_overload_gives_up_the_lowest_priority_work_first() -> None:
    windows = (WeeklyTime(0, 540, 650),)  # Room for 100 minutes before the deadlines.
    result = run(
        task("exam", 100, due_days=1, priority=4),
        task("extra", 100, due_days=0.9, priority=1),
        windows=windows,
    )
    assert minutes_for(result, "exam") == 100
    assert [r.task_id for r in result.at_risk] == ["extra"]


def test_at_risk_work_still_uses_leftover_time() -> None:
    windows = (WeeklyTime(0, 540, 880),)
    result = run(
        task("exam", 100, due_days=1, priority=4),
        task("extra", 500, due_days=1, priority=1),
        windows=windows,
    )
    assert minutes_for(result, "exam") == 100
    assert minutes_for(result, "extra") > 0
    extra = next(p for p in result.placements if p.task_id == "extra")
    assert extra.explanation.primary_reason is Reason.BEST_EFFORT


def test_overdue_task_is_reported_and_not_scheduled() -> None:
    result = run(task(minutes=100, due_days=-1))
    assert result.placements == ()
    assert [(r.shortfall_minutes, r.reason) for r in result.at_risk] == [(100, RiskReason.OVERDUE)]


def test_no_availability_reports_everything_at_risk() -> None:
    result = run(task(minutes=100, due_days=2), windows=())
    assert result.at_risk[0].shortfall_minutes == 100


def test_undated_work_is_planned_after_dated_work_competes() -> None:
    result = run(
        task("reading", 100, due_days=None),
        task("essay", 100, due_days=1, priority=2),
    )
    assert result.placements[0].task_id == "essay"
    assert result.at_risk == ()


def test_undated_work_does_not_count_as_at_risk() -> None:
    result = run(task("reading", 100000, due_days=None))
    assert result.at_risk == ()
    assert result.unplaced[0].task_id == "reading"


def test_deadline_past_the_horizon_is_not_at_risk() -> None:
    result = run(task("thesis", 5000, due_days=90), horizon_end=MONDAY + timedelta(days=7))
    assert result.at_risk == ()
    assert 0 < minutes_for(result, "thesis") < 5000


# --- Guard ----------------------------------------------------------------------------------


def test_guard_overrides_a_preference_that_would_cost_a_deadline() -> None:
    # "big" scores higher on priority, but "tight" needs this exact slot to finish on time.
    windows = (WeeklyTime(0, 540, 590), WeeklyTime(1, 540, 590))
    result = run(
        task("tight", 50, due_days=1, priority=1),
        task("big", 50, due_days=2, priority=4),
        windows=windows,
    )
    assert [p.task_id for p in result.placements] == ["tight", "big"]
    assert result.at_risk == ()


# --- Explanations ---------------------------------------------------------------------------


def test_every_placement_has_all_factors() -> None:
    for placement in run(task(minutes=200), task("b", 200, course="c2")).placements:
        assert set(placement.explanation.factors) == {
            "urgency",
            "priority",
            "course_balance",
            "variety",
        }
        assert all(0 <= value <= 1 for value in placement.explanation.factors.values())


def test_explanation_records_the_real_deadline() -> None:
    deadline = run(task(minutes=50, due_days=3)).placements[0].explanation.deadline
    assert deadline == MONDAY + timedelta(days=3)


def test_urgent_work_is_explained_by_deadline_pressure() -> None:
    placement = run(task(minutes=300, due_days=1)).placements[0]
    assert placement.explanation.primary_reason is Reason.DEADLINE_PRESSURE
    assert "%" in describe(placement.explanation)


@pytest.mark.parametrize("reason", list(Reason))
def test_every_reason_has_readable_text(reason: Reason) -> None:
    explanation = run(task(minutes=50)).placements[0].explanation
    text = describe(replace(explanation, primary_reason=reason))
    assert text.endswith(".")
    assert len(text) > 20


@pytest.mark.parametrize("reason", list(RiskReason))
def test_every_risk_has_readable_text(reason: RiskReason) -> None:
    assert describe_risk(reason).endswith(".")

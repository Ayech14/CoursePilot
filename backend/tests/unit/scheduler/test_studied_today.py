"""Time already studied today uses up that day's limit, wherever the engine checks it."""

from dataclasses import replace
from datetime import timedelta

from scheduler.models import ExistingSession, SessionClass
from scheduler.placement import WarningKind, check_placement, suggest_slots
from scheduler.planner import plan
from scheduler.repair import repair
from scheduler.timeline import build_timeline
from tests.unit.scheduler.support import MONDAY, PREFS, every_day, request, task

LIMITED = replace(PREFS, max_daily_minutes=120)
TOP_OF_DAY = MONDAY  # 08:00 UTC; the study windows open at 09:00.


def limited(**overrides):  # type: ignore[no-untyped-def]
    return request(task(minutes=2200, due_days=20), preferences=LIMITED, **overrides)


def minutes_today(result) -> int:  # type: ignore[no-untyped-def]
    return sum(
        int((s.end - s.start).total_seconds() // 60)
        for s in result.placements
        if s.start.date() == TOP_OF_DAY.date()
    )


def test_budget_for_today_shrinks() -> None:
    assert build_timeline(limited(studied_today_minutes=50)).day_budgets[:2] == (70, 120)


def test_budget_never_goes_negative() -> None:
    assert build_timeline(limited(studied_today_minutes=500)).day_budgets[0] == 0


def test_other_days_are_unaffected_when_today_is_not_in_the_timeline() -> None:
    almost_midnight = MONDAY.replace(hour=23, minute=59)
    timeline = build_timeline(
        limited(now=almost_midnight, studied_today_minutes=50, windows=every_day(0, 1440))
    )
    assert timeline.day_budgets[0] == 120


def test_planner_places_less_today() -> None:
    assert minutes_today(plan(limited())) == 100
    assert minutes_today(plan(limited(studied_today_minutes=50))) == 50
    assert minutes_today(plan(limited(studied_today_minutes=120))) == 0


def _session(hour: int, session_id: str = "s") -> ExistingSession:
    start = MONDAY.replace(hour=hour)
    return ExistingSession(
        session_id, "a", start, start + timedelta(minutes=50), SessionClass.FLEXIBLE
    )


def test_placement_warns_with_time_already_studied() -> None:
    start = MONDAY.replace(hour=10)
    end = start + timedelta(minutes=50)
    assert WarningKind.DAILY_LIMIT not in check_placement(limited(), "a", start, end).warnings
    studied = limited(studied_today_minutes=100)
    assert WarningKind.DAILY_LIMIT in check_placement(studied, "a", start, end).warnings


def test_suggestions_skip_a_full_today() -> None:
    near = MONDAY.replace(hour=10)
    slots = suggest_slots(limited(studied_today_minutes=100), "a", 50, near)
    assert slots and all(slot.start.date() != near.date() for slot in slots)


def test_repair_drops_a_session_that_no_longer_fits_today() -> None:
    kept = repair(limited(existing_sessions=(_session(10),)))
    assert all(change.session_id != "s" or change.kind.value != "remove" for change in kept.changes)
    over = repair(limited(existing_sessions=(_session(10),), studied_today_minutes=100))
    change = next(c for c in over.changes if c.session_id == "s")
    assert change.after is None or change.after.start.date() != TOP_OF_DAY.date()

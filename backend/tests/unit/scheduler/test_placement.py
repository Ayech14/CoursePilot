from dataclasses import replace
from datetime import timedelta

import pytest

from scheduler.models import ExistingSession, Interval, SessionClass, WeeklyTime
from scheduler.placement import ConflictKind, WarningKind, check_placement, suggest_slots
from tests.unit.scheduler.support import MONDAY, PREFS, request, task

# MONDAY is 08:00 UTC and availability defaults to 09:00 to 17:00 every day.
NINE = MONDAY + timedelta(hours=1)


def at(hours: float, minutes: int = 50) -> tuple:  # type: ignore[type-arg]
    start = MONDAY + timedelta(hours=hours)
    return start, start + timedelta(minutes=minutes)


def session(session_id: str, hours: float, minutes: int = 50) -> ExistingSession:
    start, end = at(hours, minutes)
    return ExistingSession(session_id, "a", start, end, SessionClass.FLEXIBLE)


def check(*sessions: ExistingSession, hours: float = 1, minutes: int = 50, **overrides: object):  # noqa: ANN201
    req = request(task(), existing_sessions=sessions, **overrides)
    start, end = at(hours, minutes)
    return check_placement(req, "a", start, end)


def test_a_clean_placement_is_ok() -> None:
    result = check()
    assert result.ok
    assert result.conflicts == ()
    assert result.warnings == ()


def test_overlap_is_a_conflict_naming_the_session() -> None:
    result = check(session("other", 1.5))
    assert [(c.kind, c.session_id) for c in result.conflicts] == [(ConflictKind.OVERLAP, "other")]


def test_touching_end_to_end_is_not_an_overlap() -> None:
    assert check(session("other", 1, 30), hours=1.5, minutes=30).conflicts == ()


def test_past_time_is_a_conflict() -> None:
    assert check(hours=-1).conflicts[0].kind is ConflictKind.IN_PAST


def test_a_session_can_be_moved_over_its_own_old_time() -> None:
    mine = session("mine", 1)
    req = request(task(), existing_sessions=(mine,))
    start, end = at(1.25)
    assert check_placement(req, "a", start, end, ignoring="mine").conflicts == ()
    assert check_placement(req, "a", start, end).conflicts != ()


def test_outside_availability_is_only_a_warning() -> None:
    result = check(hours=-0.5 + 12)
    assert result.conflicts == ()
    assert WarningKind.OUTSIDE_AVAILABILITY in result.warnings


def test_weekly_block_is_a_warning() -> None:
    result = check(weekly_blocks=(WeeklyTime(0, 540, 600),))
    assert result.warnings == (WarningKind.IN_BLOCK,)


def test_one_off_block_is_a_warning() -> None:
    start, end = at(1)
    assert check(one_off_blocks=(Interval(start, end),)).warnings == (WarningKind.IN_BLOCK,)


def test_too_close_to_another_session_is_a_warning() -> None:
    result = check(session("other", 2 - 5 / 60), hours=1, minutes=50)
    assert result.conflicts == ()
    assert result.warnings == (WarningKind.NO_BREAK,)


def test_over_the_daily_limit_is_a_warning() -> None:
    busy = session("other", 3, 340)
    result = check(busy, hours=1, minutes=50)
    assert WarningKind.DAILY_LIMIT in result.warnings


def test_past_the_deadline_is_a_warning() -> None:
    req = request(task(due_days=1 / 24 + 1 / 48))
    start, end = at(1, 50)
    assert check_placement(req, "a", start, end).warnings == (WarningKind.PAST_DEADLINE,)


# --- Suggestions ----------------------------------------------------------------------------


def suggest(*sessions: ExistingSession, hours: float = 1, minutes: int = 50, **overrides: object):  # noqa: ANN201
    req = request(task(due_days=14), existing_sessions=sessions, **overrides)
    return req, suggest_slots(req, "a", minutes, at(hours)[0])


def test_suggestions_are_valid_placements() -> None:
    req, slots = suggest(session("other", 1), session("again", 3))
    assert slots
    for slot in slots:
        assert check_placement(req, "a", slot.start, slot.end).ok


def test_suggestions_keep_the_requested_length() -> None:
    _, slots = suggest(minutes=35)
    assert all(s.end - s.start == timedelta(minutes=35) for s in slots)


def test_same_day_comes_first() -> None:
    _, slots = suggest(session("other", 1, 100))
    assert slots[0].start.date() == MONDAY.date()


def test_closest_time_comes_first() -> None:
    _, slots = suggest(session("other", 1, 50))
    assert slots[0].start == MONDAY + timedelta(hours=2)


def test_suggestions_avoid_blocks() -> None:
    start = MONDAY + timedelta(hours=1)
    block = Interval(start, start + timedelta(hours=8))
    _, slots = suggest(one_off_blocks=(block,))
    assert slots
    assert all(s.start >= block.end for s in slots)


def test_suggestions_stay_before_the_deadline() -> None:
    req = request(task(due_days=2))
    slots = suggest_slots(req, "a", 50, MONDAY + timedelta(days=5))
    assert slots
    assert all(s.end <= MONDAY + timedelta(days=2) for s in slots)


def test_full_days_are_skipped() -> None:
    prefs = replace(PREFS, max_daily_minutes=60)
    _, slots = suggest(session("other", 1, 50), preferences=prefs)
    assert slots
    assert all(s.start.date() != MONDAY.date() for s in slots)


def test_ignoring_a_session_frees_its_time() -> None:
    mine = session("mine", 1)
    req = request(task(due_days=14), existing_sessions=(mine,))
    slots = suggest_slots(req, "a", 50, mine.start, ignoring="mine")
    assert slots[0].start == mine.start


def test_limit_is_respected() -> None:
    _, slots = suggest()
    assert len(slots) == 5


@pytest.mark.parametrize("minutes", [600, 10_000])
def test_a_length_that_never_fits_gives_no_suggestions(minutes: int) -> None:
    assert suggest(minutes=minutes)[1] == ()

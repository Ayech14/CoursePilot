"""Repair, event by event, plus invariants on generated scenarios."""

from dataclasses import replace
from datetime import timedelta

import pytest

from scheduler import plan
from scheduler.models import (
    ChangeKind,
    ExistingSession,
    Explanation,
    Interval,
    Placement,
    PlanRequest,
    PlanResult,
    Reason,
    RepairReason,
    RepairResult,
    RiskReason,
    SessionClass,
    TaskInput,
    WeeklyTime,
)
from scheduler.repair import rebuild, repair
from tests.unit.scheduler.support import (
    MONDAY,
    PREFS,
    assert_invariants,
    every_day,
    random_request,
    request,
    task,
)


def planned(req: PlanRequest) -> tuple[ExistingSession, ...]:
    """Turn a fresh plan into the sessions a student would have after applying it."""
    return tuple(
        ExistingSession(f"s{i}", p.task_id, p.start, p.end, SessionClass.FLEXIBLE)
        for i, p in enumerate(plan(req).placements)
    )


def after_applying(req: PlanRequest, result: RepairResult) -> tuple[ExistingSession, ...]:
    sessions = {s.id: s for s in req.existing_sessions}
    extra: list[ExistingSession] = []
    for number, change in enumerate(result.changes):
        if change.kind is ChangeKind.REMOVE:
            del sessions[change.session_id]
        elif change.kind is ChangeKind.CREATE:
            assert change.after is not None
            extra.append(
                ExistingSession(
                    f"new{number}",
                    change.task_id,
                    change.after.start,
                    change.after.end,
                    SessionClass.FLEXIBLE,
                )
            )
        else:
            assert change.after is not None
            sessions[change.session_id] = replace(
                sessions[change.session_id], start=change.after.start, end=change.after.end
            )
    return (*sessions.values(), *extra)


def with_schedule(*tasks: TaskInput, **overrides: object) -> PlanRequest:
    req = request(*tasks, **overrides)
    return replace(req, existing_sessions=planned(req))


def kinds(result: RepairResult) -> list[ChangeKind]:
    return [c.kind for c in result.changes]


# --- Nothing happened -----------------------------------------------------------------------


def test_a_valid_schedule_is_left_alone() -> None:
    req = with_schedule(task("a", 400, due_days=10), task("b", 300, due_days=14, course="c2"))
    result = repair(req)
    assert result.changes == ()
    assert result.unchanged == len(req.existing_sessions)


def test_empty_schedule_is_generated() -> None:
    result = repair(request(task("a", 100)))
    assert set(kinds(result)) == {ChangeKind.CREATE}


# --- Each kind of event ---------------------------------------------------------------------


def test_missed_session_only_adds_its_time_back() -> None:
    req = with_schedule(task("a", 300, due_days=14))
    missed, *others = req.existing_sessions  # The student has lost this one.
    req = replace(req, existing_sessions=tuple(others))

    result = repair(req)

    assert kinds(result) == [ChangeKind.CREATE]
    assert result.changes[0].after is not None
    assert result.unchanged == len(others)
    created = result.changes[0].after
    assert (created.end - created.start) == (missed.end - missed.start)


def test_task_running_long_only_adds_sessions() -> None:
    req = with_schedule(task("a", 200, due_days=14), task("b", 200, due_days=14, course="c2"))
    longer = replace(req, tasks=(task("a", 300, due_days=14), req.tasks[1]))

    result = repair(longer)

    assert set(kinds(result)) == {ChangeKind.CREATE}
    assert result.unchanged == len(req.existing_sessions)


def test_finished_task_loses_only_its_own_sessions() -> None:
    req = with_schedule(task("a", 200, due_days=14), task("b", 200, due_days=14, course="c2"))
    finished = replace(req, tasks=(req.tasks[1],))

    result = repair(finished)

    assert set(kinds(result)) == {ChangeKind.REMOVE}
    assert all(c.task_id == "a" for c in result.changes)
    assert all(c.reason is RepairReason.TASK_FINISHED for c in result.changes)


def test_less_work_removes_the_latest_sessions() -> None:
    req = with_schedule(task("a", 200, due_days=14))
    less = replace(req, tasks=(task("a", 100, due_days=14),))

    result = repair(less)

    last_two = sorted(req.existing_sessions, key=lambda s: s.start)[-2:]
    assert {c.session_id for c in result.changes} == {s.id for s in last_two}
    assert all(c.reason is RepairReason.LESS_WORK_NEEDED for c in result.changes)


def test_slightly_less_work_shortens_a_session() -> None:
    req = with_schedule(task("a", 200, due_days=14))
    less = replace(req, tasks=(task("a", 180, due_days=14),))

    result = repair(less)

    assert kinds(result) == [ChangeKind.RESIZE]
    change = result.changes[0]
    assert change.before is not None and change.after is not None
    assert change.after.start == change.before.start
    assert (change.before.end - change.after.end) == timedelta(minutes=20)


def test_new_exam_fits_around_the_existing_plan() -> None:
    req = with_schedule(
        task("a", 200, due_days=14), preferences=replace(PREFS, max_daily_minutes=480)
    )
    with_exam = replace(req, tasks=(*req.tasks, task("exam", 150, due_days=3, course="c2")))

    result = repair(with_exam)

    assert set(kinds(result)) == {ChangeKind.CREATE}
    assert result.unchanged == len(req.existing_sessions)
    assert result.at_risk == ()


def test_earlier_deadline_moves_only_sessions_now_too_late() -> None:
    req = with_schedule(task("a", 400, due_days=14))
    last = max(req.existing_sessions, key=lambda s: s.start)
    earlier = replace(req, tasks=(TaskInput("a", 400, 2, last.start, "c1"),))

    result = repair(earlier)

    moved = [c for c in result.changes if c.kind is ChangeKind.MOVE]
    assert moved
    assert all(c.reason is RepairReason.PAST_DEADLINE for c in moved)
    assert result.unchanged == len(req.existing_sessions) - len(moved)
    assert result.at_risk == ()


def test_later_deadline_changes_nothing() -> None:
    req = with_schedule(task("a", 300, due_days=7))
    later = replace(req, tasks=(task("a", 300, due_days=21),))
    assert repair(later).changes == ()


def test_lost_availability_moves_only_the_affected_day() -> None:
    req = with_schedule(task("a", 300, due_days=14))
    victim_day = req.existing_sessions[0].start.weekday()
    windows = tuple(w for w in every_day() if w.day_of_week != victim_day)
    affected = [s for s in req.existing_sessions if s.start.weekday() == victim_day]

    result = repair(replace(req, windows=windows))

    assert {c.session_id for c in result.changes} == {s.id for s in affected}
    assert all(c.reason is RepairReason.OUTSIDE_AVAILABILITY for c in result.changes)
    assert all(c.kind is ChangeKind.MOVE for c in result.changes)


def test_new_block_moves_only_what_it_covers() -> None:
    req = with_schedule(task("a", 300, due_days=14))
    victim = req.existing_sessions[1]

    result = repair(replace(req, one_off_blocks=(Interval(victim.start, victim.end),)))

    assert [c.session_id for c in result.changes] == [victim.id]
    assert result.changes[0].reason is RepairReason.TIME_BLOCKED
    assert result.changes[0].kind is ChangeKind.MOVE


def test_lower_daily_limit_drops_the_excess() -> None:
    prefs = replace(PREFS, max_daily_minutes=480)
    req = with_schedule(task("a", 900, due_days=2), preferences=prefs)
    result = repair(replace(req, preferences=replace(PREFS, max_daily_minutes=200)))
    reasons = {c.reason for c in result.changes}
    assert RepairReason.DAILY_LIMIT in reasons


# --- Protected sessions ---------------------------------------------------------------------


def _class_first(req: PlanRequest, session_class: SessionClass) -> PlanRequest:
    first, *rest = req.existing_sessions
    return replace(req, existing_sessions=(replace(first, session_class=session_class), *rest))


@pytest.mark.parametrize("session_class", [SessionClass.LOCKED, SessionClass.STICKY])
def test_protected_session_in_a_blocked_time_stays(session_class: SessionClass) -> None:
    req = _class_first(with_schedule(task("a", 300, due_days=14)), session_class)
    first = req.existing_sessions[0]
    result = repair(replace(req, one_off_blocks=(Interval(first.start, first.end),)))
    assert first.id not in {c.session_id for c in result.changes}


def test_flexible_sessions_yield_to_protected_ones_with_a_break() -> None:
    req = with_schedule(task("a", 300, due_days=14))
    victim = req.existing_sessions[0]
    pinned = ExistingSession(
        "pin",
        "a",
        victim.end,
        victim.end + timedelta(minutes=30),
        SessionClass.LOCKED,
    )
    req = replace(req, existing_sessions=(*req.existing_sessions, pinned))
    assert victim.id in {c.session_id for c in repair(req).changes}


# --- Pressure -------------------------------------------------------------------------------


def _crowded() -> PlanRequest:
    """Monday to Wednesday are full of a far-off task when an urgent exam appears."""
    windows = tuple(WeeklyTime(day, 540, 760) for day in range(7))
    req = with_schedule(
        task("far", 1500, due_days=20, course="c1"),
        windows=windows,
        preferences=replace(PREFS, max_daily_minutes=200),
    )
    return replace(req, tasks=(*req.tasks, task("exam", 300, due_days=2, priority=4, course="c2")))


def test_valid_sessions_move_only_when_a_deadline_needs_it() -> None:
    req = _crowded()
    result = repair(req)
    assert result.at_risk == ()
    moved = [c for c in result.changes if c.kind is ChangeKind.MOVE]
    assert moved
    assert all(c.reason is RepairReason.MAKING_ROOM for c in moved)
    assert all(c.task_id == "far" for c in moved)
    assert result.unchanged > 0


def test_nothing_moves_for_a_task_that_cannot_be_saved() -> None:
    req = with_schedule(task("a", 200, due_days=14))
    hopeless = TaskInput("x", 500, 2, MONDAY + timedelta(minutes=30), "c2")
    result = repair(replace(req, tasks=(*req.tasks, hopeless)))
    assert result.changes == ()
    assert [(r.task_id, r.reason) for r in result.at_risk] == [("x", RiskReason.INSUFFICIENT_TIME)]


def test_sticky_is_released_last_and_flagged() -> None:
    # Monday holds two sessions and Tuesday one, so "mine" can move but "urgent" cannot.
    windows = (WeeklyTime(0, 540, 650), WeeklyTime(1, 540, 590))
    urgent = task("urgent", 100, due_days=1, priority=4, course="c2")
    other = task("other", 50, due_days=3, priority=1)
    sticky = ExistingSession(
        "mine",
        "other",
        MONDAY + timedelta(hours=1),
        MONDAY + timedelta(hours=1, minutes=50),
        SessionClass.STICKY,
    )
    req = request(urgent, other, windows=windows, existing_sessions=(sticky,))

    result = repair(req)

    released = [c for c in result.changes if c.sticky_released]
    assert [c.session_id for c in released] == ["mine"]
    assert result.at_risk == ()


def test_sticky_stays_when_releasing_it_would_not_help() -> None:
    windows = (WeeklyTime(0, 540, 650),)
    urgent = task("urgent", 100, due_days=1, priority=4, course="c2")
    other = task("other", 50, due_days=1, priority=1)
    sticky = ExistingSession(
        "mine",
        "other",
        MONDAY + timedelta(hours=1),
        MONDAY + timedelta(hours=1, minutes=50),
        SessionClass.STICKY,
    )
    result = repair(request(urgent, other, windows=windows, existing_sessions=(sticky,)))
    assert "mine" not in {c.session_id for c in result.changes}


def test_locked_session_is_never_released_even_to_save_a_deadline() -> None:
    windows = (WeeklyTime(0, 540, 650),)
    urgent = task("urgent", 100, due_days=1, priority=4, course="c2")
    other = task("other", 50, due_days=1, priority=1)
    locked = ExistingSession(
        "mine",
        "other",
        MONDAY + timedelta(hours=1),
        MONDAY + timedelta(hours=1, minutes=50),
        SessionClass.LOCKED,
    )
    result = repair(request(urgent, other, windows=windows, existing_sessions=(locked,)))
    assert "mine" not in {c.session_id for c in result.changes}
    assert any(r.task_id == "urgent" for r in result.at_risk)


# --- Rebuild --------------------------------------------------------------------------------


def test_repeated_updates_do_not_keep_adding_open_ended_work() -> None:
    req = with_schedule(task("reading", 5000, due_days=None))
    assert repair(req).changes == ()


def test_shortened_then_released_session_is_a_single_change() -> None:
    windows = tuple(WeeklyTime(day, 540, 760) for day in range(7))
    prefs = replace(PREFS, max_daily_minutes=200)
    req = with_schedule(task("far", 1500, due_days=20), windows=windows, preferences=prefs)
    crowded = replace(
        req,
        tasks=(
            task("far", 1480, due_days=20),
            task("exam", 400, due_days=2, priority=4, course="c2"),
        ),
    )
    ids = [c.session_id for c in repair(crowded).changes if c.session_id]
    assert len(ids) == len(set(ids))


def test_rebuild_of_an_unchanged_plan_changes_nothing() -> None:
    assert rebuild(with_schedule(task("a", 300))).changes == ()


def test_rebuild_pairs_replaced_sessions_as_moves() -> None:
    req = with_schedule(task("a", 200, due_days=14))
    shifted = tuple(
        replace(s, start=s.start + timedelta(hours=2), end=s.end + timedelta(hours=2))
        for s in req.existing_sessions
    )
    result = rebuild(replace(req, existing_sessions=shifted))
    assert kinds(result)
    assert set(kinds(result)) == {ChangeKind.MOVE}
    assert all(c.reason is RepairReason.REBUILT for c in result.changes)


def test_rebuild_keeps_protected_sessions() -> None:
    req = _class_first(with_schedule(task("a", 200, due_days=14)), SessionClass.STICKY)
    first = req.existing_sessions[0]
    moved = replace(first, start=first.start + timedelta(days=3), end=first.end + timedelta(days=3))
    req = replace(req, existing_sessions=(moved, *req.existing_sessions[1:]))
    assert moved.id not in {c.session_id for c in rebuild(req).changes}


# --- Generated scenarios --------------------------------------------------------------------


SEEDS = range(500)
_NOTE = Explanation(Reason.VARIETY, {"urgency": 0.0}, False, None)


def _assert_final_state(req: PlanRequest, result: RepairResult) -> tuple[ExistingSession, ...]:
    final = after_applying(req, result)
    released = {c.session_id for c in result.changes if c.sticky_released}
    protected = tuple(
        s for s in final if s.session_class is not SessionClass.FLEXIBLE and s.id not in released
    )
    automatic = tuple(
        Placement(s.task_id, s.start, s.end, _NOTE)
        for s in final
        if s.session_class is SessionClass.FLEXIBLE or s.id in released
    )
    assert_invariants(
        replace(req, existing_sessions=protected),
        PlanResult(automatic, result.at_risk, result.unplaced),
    )
    return final


@pytest.mark.parametrize("seed", SEEDS)
def test_repaired_schedules_obey_every_rule(seed: int) -> None:
    req = random_request(seed)
    _assert_final_state(req, repair(req))


@pytest.mark.parametrize("seed", SEEDS)
def test_rebuilt_schedules_obey_every_rule(seed: int) -> None:
    req = random_request(seed)
    _assert_final_state(req, rebuild(req))


@pytest.mark.parametrize("seed", SEEDS)
def test_locked_sessions_are_never_touched(seed: int) -> None:
    req = random_request(seed)
    locked = {s.id for s in req.existing_sessions if s.session_class is SessionClass.LOCKED}
    for result in (repair(req), rebuild(req)):
        assert not locked & {c.session_id for c in result.changes}


@pytest.mark.parametrize("seed", SEEDS)
def test_repairing_a_repaired_schedule_changes_nothing(seed: int) -> None:
    req = random_request(seed)
    final = after_applying(req, repair(req))
    again = repair(replace(req, existing_sessions=final))
    assert again.changes == ()


@pytest.mark.parametrize("seed", SEEDS)
def test_repair_saves_as_much_work_as_a_rebuild(seed: int) -> None:
    def short(result: RepairResult) -> int:
        return sum(r.shortfall_minutes for r in result.at_risk if r.reason != "overdue")

    req = random_request(seed)
    assert short(repair(req)) <= short(rebuild(req))


@pytest.mark.parametrize("seed", SEEDS)
def test_repair_is_deterministic(seed: int) -> None:
    req = random_request(seed)
    assert repr(repair(req)) == repr(repair(req))


def test_generated_scenarios_include_real_repairs() -> None:
    """Guards the properties above against passing because nothing happened."""
    changed = sum(1 for seed in SEEDS if repair(random_request(seed)).changes)
    existing = sum(1 for seed in SEEDS if random_request(seed).existing_sessions)
    assert changed > 100
    assert existing > 100

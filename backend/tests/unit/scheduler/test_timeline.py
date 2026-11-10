from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from scheduler.models import ExistingSession, Interval, SessionClass, WeeklyTime
from scheduler.timeline import (
    build_timeline,
    local_to_utc,
    merge_intervals,
    round_up_to_snap,
    subtract_intervals,
)
from tests.unit.scheduler.support import MONDAY, PREFS, request


def at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 2, 2, hour, minute, tzinfo=UTC)


def interval(a: int, b: int) -> Interval:
    return Interval(at(a), at(b))


def slot_times(req):  # noqa: ANN001, ANN201
    timeline = build_timeline(req)
    return [(timeline.to_instant(s.start), timeline.to_instant(s.end)) for s in timeline.slots]


# --- Daylight saving ------------------------------------------------------------------------


TORONTO = ZoneInfo("America/Toronto")


def test_ordinary_time_converts() -> None:
    assert local_to_utc(date(2026, 1, 15), 540, TORONTO) == datetime(2026, 1, 15, 14, 0, tzinfo=UTC)


def test_offset_changes_with_the_season() -> None:
    assert local_to_utc(date(2026, 7, 15), 540, TORONTO) == datetime(2026, 7, 15, 13, 0, tzinfo=UTC)


@pytest.mark.parametrize("minute", [120, 150, 179])
def test_time_inside_spring_gap_snaps_to_end_of_gap(minute: int) -> None:
    # On 2026-03-08 Toronto jumps from 02:00 to 03:00, at 07:00 UTC.
    assert local_to_utc(date(2026, 3, 8), minute, TORONTO) == datetime(2026, 3, 8, 7, tzinfo=UTC)


def test_repeated_hour_uses_first_occurrence() -> None:
    # On 2026-11-01 01:30 happens twice in Toronto; first in EDT, UTC-4.
    assert local_to_utc(date(2026, 11, 1), 90, TORONTO) == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)


def test_half_hour_shift_gap() -> None:
    # Lord Howe jumps from 02:00 to 02:30 on 2026-10-04, at 15:30 UTC the day before.
    zone = ZoneInfo("Australia/Lord_Howe")
    assert local_to_utc(date(2026, 10, 4), 135, zone) == datetime(2026, 10, 3, 15, 30, tzinfo=UTC)


def test_gap_at_midnight() -> None:
    # Havana jumps from 00:00 to 01:00 on 2026-03-08.
    zone = ZoneInfo("America/Havana")
    assert local_to_utc(date(2026, 3, 8), 0, zone) == datetime(2026, 3, 8, 5, tzinfo=UTC)


def test_minute_1440_is_the_next_midnight() -> None:
    assert local_to_utc(date(2026, 1, 15), 1440, TORONTO) == local_to_utc(
        date(2026, 1, 16), 0, TORONTO
    )


def _study_minutes_on(day: datetime, windows, zone: str) -> int:  # noqa: ANN001
    req = request(
        now=day,
        horizon_end=day + timedelta(days=1),
        timezone=zone,
        windows=windows,
        preferences=replace(PREFS, preferred_session_minutes=60, break_minutes=0),
    )
    return sum(s.minutes for s in build_timeline(req).slots)


def test_spring_forward_day_loses_an_hour_of_a_window_across_the_gap() -> None:
    # 01:00 to 04:00 on the day clocks jump is only two real hours long.
    midnight = datetime(2026, 3, 8, 5, tzinfo=UTC)
    assert _study_minutes_on(midnight, (WeeklyTime(6, 60, 240),), "America/Toronto") == 120


def test_fall_back_day_gains_an_hour_in_a_window_across_the_repeat() -> None:
    midnight = datetime(2026, 11, 1, 4, tzinfo=UTC)
    assert _study_minutes_on(midnight, (WeeklyTime(6, 60, 240),), "America/Toronto") == 240


def test_morning_window_keeps_its_wall_clock_time_across_the_change() -> None:
    before = datetime(2026, 3, 7, 5, tzinfo=UTC)
    req = request(
        now=before,
        horizon_end=before + timedelta(days=3),
        timezone="America/Toronto",
        windows=tuple(WeeklyTime(d, 540, 600) for d in range(7)),
    )
    local = [s.astimezone(TORONTO).strftime("%H:%M") for s, _ in slot_times(req)]
    assert set(local) == {"09:00"}
    utc_hours = [s.hour for s, _ in slot_times(req)]
    assert utc_hours[0] == 14
    assert utc_hours[1] == 13


# --- Interval helpers -----------------------------------------------------------------------


def test_merge_joins_overlapping_and_adjacent() -> None:
    merged = merge_intervals(
        [interval(13, 15), interval(9, 11), interval(11, 12), interval(10, 11)]
    )
    assert merged == [interval(9, 12), interval(13, 15)]


def test_merge_ignores_empty_intervals() -> None:
    assert merge_intervals([interval(9, 9)]) == []


@pytest.mark.parametrize(
    ("cuts", "expected"),
    [
        ([], [(9, 17)]),
        ([(11, 12)], [(9, 11), (12, 17)]),
        ([(8, 10)], [(10, 17)]),
        ([(16, 18)], [(9, 16)]),
        ([(8, 18)], []),
        ([(10, 11), (13, 14)], [(9, 10), (11, 13), (14, 17)]),
        ([(18, 19)], [(9, 17)]),
    ],
)
def test_subtract(cuts: list[tuple[int, int]], expected: list[tuple[int, int]]) -> None:
    result = subtract_intervals([interval(9, 17)], [interval(*c) for c in cuts])
    assert result == [interval(*e) for e in expected]


# --- Slots ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("second", "expected_second", "expected_minute"),
    [(0, 0, 0), (1, 0, 5), (299, 0, 5)],
)
def test_round_up_to_five_minutes(second: int, expected_second: int, expected_minute: int) -> None:
    rounded = round_up_to_snap(MONDAY + timedelta(seconds=second))
    assert rounded.minute == expected_minute
    assert rounded.second == expected_second


def test_slots_follow_session_and_break_length() -> None:
    req = request(windows=(WeeklyTime(0, 540, 720),), horizon_end=MONDAY + timedelta(days=1))
    assert [(s.strftime("%H:%M"), e.strftime("%H:%M")) for s, e in slot_times(req)] == [
        ("09:00", "09:50"),
        ("10:00", "10:50"),
        ("11:00", "11:50"),
    ]


def test_short_remainder_is_kept_only_if_long_enough() -> None:
    kept = request(windows=(WeeklyTime(0, 540, 630),), horizon_end=MONDAY + timedelta(days=1))
    dropped = request(windows=(WeeklyTime(0, 540, 620),), horizon_end=MONDAY + timedelta(days=1))
    assert len(slot_times(kept)) == 2  # 50 minutes, a break, then 30.
    assert len(slot_times(dropped)) == 1


def test_weekly_block_is_removed() -> None:
    req = request(
        windows=(WeeklyTime(0, 540, 720),),
        weekly_blocks=(WeeklyTime(0, 600, 660),),
        horizon_end=MONDAY + timedelta(days=1),
    )
    starts = [s.strftime("%H:%M") for s, _ in slot_times(req)]
    assert starts == ["09:00", "11:00"]


def test_one_off_block_is_removed() -> None:
    req = request(
        windows=(WeeklyTime(0, 540, 720),),
        one_off_blocks=(Interval(at(10), at(11)),),
        horizon_end=MONDAY + timedelta(days=1),
    )
    assert [s.strftime("%H:%M") for s, _ in slot_times(req)] == ["09:00", "11:00"]


def test_kept_session_blocks_time_with_a_break_around_it() -> None:
    kept = ExistingSession("s", "a", at(10), at(10, 50), SessionClass.LOCKED)
    req = request(
        windows=(WeeklyTime(0, 540, 780),),
        existing_sessions=(kept,),
        horizon_end=MONDAY + timedelta(days=1),
    )
    starts = [s.strftime("%H:%M") for s, _ in slot_times(req)]
    assert starts == ["09:00", "11:00", "12:00"]  # 09:50 to 11:00 is the session and its breaks.


def test_flexible_session_does_not_block_time() -> None:
    session = ExistingSession("s", "a", at(9), at(9, 50), SessionClass.FLEXIBLE)
    req = request(
        windows=(WeeklyTime(0, 540, 600),),
        existing_sessions=(session,),
        horizon_end=MONDAY + timedelta(days=1),
    )
    assert len(slot_times(req)) == 1


def test_kept_sessions_reduce_the_days_budget() -> None:
    kept = ExistingSession("s", "a", at(18), at(19), SessionClass.STICKY)
    req = request(existing_sessions=(kept,), horizon_end=MONDAY + timedelta(days=1))
    assert build_timeline(req).day_budgets[0] == PREFS.max_daily_minutes - 60


def test_nothing_before_now() -> None:
    req = request(
        now=at(10, 2),
        windows=(WeeklyTime(0, 540, 720),),
        horizon_end=MONDAY + timedelta(days=1),
    )
    assert slot_times(req)[0][0] == at(10, 5)


def test_nothing_after_the_horizon() -> None:
    req = request(windows=(WeeklyTime(0, 540, 720),), horizon_end=at(10))
    assert slot_times(req) == [(at(9), at(9, 50))]


def test_break_holds_across_local_midnight() -> None:
    req = request(
        windows=(WeeklyTime(0, 1390, 1440), WeeklyTime(1, 0, 120)),
        horizon_end=MONDAY + timedelta(days=2),
    )
    (_, first_end), (second_start, _) = slot_times(req)[:2]
    assert second_start - first_end >= timedelta(minutes=PREFS.break_minutes)


def test_no_windows_means_no_slots() -> None:
    assert slot_times(request(windows=())) == []

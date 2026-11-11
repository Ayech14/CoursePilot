"""Reading calendar files into busy times and deadlines."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from app.services.ics import IcsError, parse

TORONTO = ZoneInfo("America/Toronto")
START = datetime(2026, 11, 9, tzinfo=UTC)
END = START + timedelta(days=35)


def calendar(*events: str, extra: str = "") -> bytes:
    body = "".join(f"BEGIN:VEVENT\r\n{e.strip()}\r\nEND:VEVENT\r\n" for e in events)
    return (
        "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\n"
        + extra
        + body
        + "END:VCALENDAR\r\n"
    ).encode()


def event(
    uid: str, start: str, end: str | None = None, summary: str = "Thing", **extra: str
) -> str:
    lines = [f"UID:{uid}", f"SUMMARY:{summary}", f"DTSTART{start}"]
    if end is not None:
        lines.append(f"DTEND{end}")
    lines += [f"{key.replace('_', '-')}:{value}" for key, value in extra.items()]
    return "\r\n".join(lines)


def test_timed_events_are_busy_time() -> None:
    parsed = parse(
        calendar(event("a", ":20261110T150000Z", ":20261110T163000Z", "Shift")), TORONTO, START, END
    )
    assert [(b.title, b.start, b.end) for b in parsed.busy] == [
        (
            "Shift",
            datetime(2026, 11, 10, 15, tzinfo=UTC),
            datetime(2026, 11, 10, 16, 30, tzinfo=UTC),
        )
    ]
    assert parsed.deadlines == []


def test_moodle_style_due_items_are_deadlines() -> None:
    due = event(
        "123@eclass.yorku.ca",
        ":20261120T045900Z",
        ":20261120T045900Z",
        "Assignment 2 is due",
        CATEGORIES="EECS2030 M",
    )
    parsed = parse(calendar(due), TORONTO, START, END)
    assert parsed.busy == []
    [deadline] = parsed.deadlines
    assert deadline.title == "Assignment 2 is due"
    assert deadline.due == datetime(2026, 11, 20, 4, 59, tzinfo=UTC)
    assert deadline.hints == ("EECS2030 M",)


def test_an_event_with_no_end_is_a_deadline() -> None:
    parsed = parse(calendar(event("a", ":20261110T150000Z")), TORONTO, START, END)
    assert len(parsed.deadlines) == 1


def test_duration_gives_the_end() -> None:
    parsed = parse(calendar(event("a", ":20261110T150000Z", DURATION="PT2H")), TORONTO, START, END)
    assert parsed.busy[0].end == datetime(2026, 11, 10, 17, tzinfo=UTC)


def test_all_day_events_are_skipped_and_counted() -> None:
    holiday = event("h", ";VALUE=DATE:20261111", ";VALUE=DATE:20261112", "Remembrance Day")
    parsed = parse(calendar(holiday), TORONTO, START, END)
    assert (parsed.busy, parsed.deadlines, parsed.skipped_all_day) == ([], [], 1)


@pytest.mark.parametrize("extra", [{"STATUS": "CANCELLED"}, {"TRANSP": "TRANSPARENT"}])
def test_cancelled_and_free_events_are_skipped(extra: dict[str, str]) -> None:
    item = event("a", ":20261110T150000Z", ":20261110T160000Z", **extra)
    assert parse(calendar(item), TORONTO, START, END).busy == []


def test_floating_times_are_read_in_the_students_zone() -> None:
    parsed = parse(
        calendar(event("a", ":20261110T090000", ":20261110T100000")), TORONTO, START, END
    )
    assert parsed.busy[0].start == datetime(2026, 11, 10, 14, tzinfo=UTC)


def test_named_zones_are_respected() -> None:
    item = event("a", ";TZID=Europe/Paris:20261110T090000", ";TZID=Europe/Paris:20261110T100000")
    parsed = parse(calendar(item), TORONTO, START, END)
    assert parsed.busy[0].start == datetime(2026, 11, 10, 8, tzinfo=UTC)


def test_weekly_lectures_expand_with_exceptions_and_keep_local_time_across_dst() -> None:
    # Mondays 10:00 Toronto from Oct 26, skipping Nov 16. Clocks change on Nov 1.
    lecture = event(
        "lec",
        ";TZID=America/Toronto:20261026T100000",
        ";TZID=America/Toronto:20261026T112000",
        "EECS 2030 Lecture",
        RRULE="FREQ=WEEKLY;COUNT=6",
        EXDATE=";TZID=America/Toronto:20261116T100000".lstrip(";"),
    )
    lecture = lecture.replace("EXDATE:TZID=", "EXDATE;TZID=")
    parsed = parse(calendar(lecture), TORONTO, datetime(2026, 10, 20, tzinfo=UTC), END)
    starts = [b.start.astimezone(TORONTO).strftime("%m-%d %H:%M") for b in parsed.busy]
    assert starts == ["10-26 10:00", "11-02 10:00", "11-09 10:00", "11-23 10:00", "11-30 10:00"]
    assert len({b.uid for b in parsed.busy}) == 5


def test_only_the_requested_range_is_read() -> None:
    later = event("a", ":20270301T150000Z", ":20270301T160000Z")
    assert parse(calendar(later), TORONTO, START, END).busy == []


def test_missing_titles_get_a_plain_label() -> None:
    item = "UID:x\r\nDTSTART:20261110T150000Z\r\nDTEND:20261110T160000Z"
    assert parse(calendar(item), TORONTO, START, END).busy[0].title == "Busy"


@pytest.mark.parametrize("data", [b"", b"<html>Sign in</html>", b"BEGIN:VCALENDAR\r\nBEGIN:VEVENT"])
def test_anything_that_is_not_a_calendar_is_refused(data: bytes) -> None:
    with pytest.raises(IcsError):
        parse(data, TORONTO, START, END)

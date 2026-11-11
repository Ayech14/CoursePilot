"""Connected calendars, deadline suggestions and busy times through the API.

The network is replaced by a dictionary of links, so these tests are about what happens with a
calendar's contents. The fetcher's own safety is tested in tests/unit/calendar.
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services import feed_fetch
from app.services.scheduling import utc_now
from tests.integration.helpers import API, Headers, field_errors, new_course, new_user

NOW = datetime(2026, 11, 9, 12, 0, tzinfo=UTC)  # A Monday.
FEEDS = f"{API}/calendar-feeds"
SUGGESTIONS = f"{API}/deadline-suggestions"
LINK = "https://eclass.example.ca/calendar/export_execute.php?userid=1&authtoken=secret123"

SHIFT = "UID:shift-1\r\nSUMMARY:Work shift\r\nDTSTART:20261110T220000Z\r\nDTEND:20261111T020000Z"
LECTURE = (
    "UID:lec\r\nSUMMARY:EECS 2030 Lecture\r\n"
    "DTSTART;TZID=America/Toronto:20261109T100000\r\nDTEND;TZID=America/Toronto:20261109T112000\r\n"
    "RRULE:FREQ=WEEKLY;COUNT=3"
)
DUE = (
    "UID:a2@eclass\r\nSUMMARY:Assignment 2 is due\r\nCATEGORIES:EECS2030 M\r\n"
    "DTSTART:20261120T045900Z\r\nDTEND:20261120T045900Z"
)
PAST_DUE = (
    "UID:old@eclass\r\nSUMMARY:Old quiz\r\nDTSTART:20261101T045900Z\r\nDTEND:20261101T045900Z"
)


def calendar(*events: str) -> bytes:
    body = "".join(f"BEGIN:VEVENT\r\n{e}\r\nEND:VEVENT\r\n" for e in events)
    return f"BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//t//EN\r\n{body}END:VCALENDAR\r\n".encode()


class FakeInternet:
    def __init__(self) -> None:
        self.pages: dict[str, bytes | Exception] = {}
        self.requests: list[str] = []

    def fetch(self, url: str) -> bytes:
        self.requests.append(url)
        page = self.pages.get(
            feed_fetch.normalize_url(url), feed_fetch.FeedFetchError("Not found.")
        )
        if isinstance(page, Exception):
            raise page
        return page


@pytest.fixture
def internet(monkeypatch: pytest.MonkeyPatch) -> FakeInternet:
    fake = FakeInternet()
    monkeypatch.setattr(feed_fetch, "fetch_calendar", fake.fetch)
    return fake


@pytest.fixture(autouse=True)
def frozen_time(client: TestClient) -> Iterator[None]:
    set_time(client, NOW)
    yield


def set_time(client: TestClient, moment: datetime) -> None:
    client.app.dependency_overrides[utc_now] = lambda: moment  # type: ignore[attr-defined]


def connect(client: TestClient, headers: Headers, url: str = LINK, name: str = "eClass") -> Any:
    return client.post(FEEDS, json={"name": name, "url": url}, headers=headers)


def busy(client: TestClient, headers: Headers, days: int = 14) -> list[dict[str, Any]]:
    response = client.get(
        f"{API}/busy-times",
        params={"start": NOW.isoformat(), "end": (NOW + timedelta(days=days)).isoformat()},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_connecting_imports_busy_time_and_hides_the_link(
    client: TestClient, internet: FakeInternet
) -> None:
    internet.pages[LINK] = calendar(SHIFT, LECTURE, DUE)
    headers = new_user(client)
    response = connect(client, headers)
    assert response.status_code == 201, response.text
    feed = response.json()
    assert feed["url_hint"] == "eclass.example.ca/…"
    assert "secret123" not in response.text
    # Three lectures and a shift fall within the planning horizon.
    assert (feed["busy_count"], feed["pending_deadlines"]) == (4, 1)
    assert feed["last_error"] is None

    imported = [b for b in busy(client, headers) if b["source"] == "calendar"]
    assert [b["title"] for b in imported] == [
        "EECS 2030 Lecture",
        "Work shift",
        "EECS 2030 Lecture",
    ]
    assert {b["feed_name"] for b in imported} == {"eClass"}
    assert client.get(FEEDS, headers=headers).json() == [feed]


def test_webcal_links_work(client: TestClient, internet: FakeInternet) -> None:
    internet.pages[LINK] = calendar(SHIFT)
    response = connect(client, new_user(client), LINK.replace("https://", "webcal://"))
    assert response.status_code == 201


def test_a_link_that_fails_is_not_saved(client: TestClient, internet: FakeInternet) -> None:
    headers = new_user(client)
    assert field_errors(connect(client, headers))["url"] == "Not found."
    internet.pages[LINK] = b"<html>Please sign in</html>"
    assert "calendar file" in field_errors(connect(client, headers))["url"]
    assert client.get(FEEDS, headers=headers).json() == []


@pytest.mark.parametrize(
    "url", ["http://example.com/a.ics", "javascript:alert(1)", "https://10.0.0.1:8080/"]
)
def test_unsafe_links_are_refused_before_any_request(
    client: TestClient, internet: FakeInternet, url: str
) -> None:
    assert "url" in field_errors(connect(client, new_user(client), url))
    assert internet.requests == []


def test_the_same_link_cannot_be_added_twice(client: TestClient, internet: FakeInternet) -> None:
    internet.pages[LINK] = calendar(SHIFT)
    headers = new_user(client)
    connect(client, headers)
    assert field_errors(connect(client, headers, LINK.replace("https", "webcal")))["url"] == (
        "This calendar is already connected."
    )


def test_imported_busy_time_shapes_the_schedule(client: TestClient, internet: FakeInternet) -> None:
    headers = new_user(client, "UTC")
    windows = [{"day_of_week": d, "start_minute": 0, "end_minute": 1440} for d in range(7)]
    client.put(f"{API}/availability/windows", json={"windows": windows}, headers=headers)
    client.post(
        f"{API}/tasks",
        json={
            "title": "Read",
            "task_type": "reading",
            "estimated_minutes": 3000,
            "deadline_at": "2026-11-12T00:00:00Z",
        },
        headers=headers,
    )
    internet.pages[LINK] = calendar(SHIFT)
    connect(client, headers)
    proposal = client.post(f"{API}/schedule/preview", headers=headers).json()
    shift_start, shift_end = "2026-11-10T22:00:00Z", "2026-11-11T02:00:00Z"
    for change in proposal["changes"]:
        assert change["after_end_at"] <= shift_start or change["after_start_at"] >= shift_end


def test_syncing_replaces_events_and_makes_open_previews_stale(
    client: TestClient, internet: FakeInternet
) -> None:
    internet.pages[LINK] = calendar(SHIFT)
    headers = new_user(client)
    feed = connect(client, headers).json()
    proposal = client.post(f"{API}/schedule/preview", headers=headers).json()

    moved = SHIFT.replace("20261110T220000Z", "20261112T220000Z").replace(
        "20261111T020000Z", "20261113T020000Z"
    )
    internet.pages[LINK] = calendar(moved)
    synced = client.post(f"{FEEDS}/{feed['id']}/sync", headers=headers).json()
    assert synced["busy_count"] == 1
    [shift] = [b for b in busy(client, headers) if b["source"] == "calendar"]
    assert shift["start_at"].startswith("2026-11-12T22:00")
    apply = client.post(f"{API}/schedule/proposals/{proposal['id']}/apply", headers=headers)
    assert apply.json()["error"]["code"] == "proposal_stale"


def test_an_unchanged_calendar_does_not_disturb_previews(
    client: TestClient, internet: FakeInternet
) -> None:
    internet.pages[LINK] = calendar(SHIFT)
    headers = new_user(client)
    feed = connect(client, headers).json()
    proposal = client.post(f"{API}/schedule/preview", headers=headers).json()
    client.post(f"{FEEDS}/{feed['id']}/sync", headers=headers)
    apply = client.post(f"{API}/schedule/proposals/{proposal['id']}/apply", headers=headers)
    assert apply.status_code == 200


def test_a_failed_sync_keeps_the_last_good_events(
    client: TestClient, internet: FakeInternet
) -> None:
    internet.pages[LINK] = calendar(SHIFT)
    headers = new_user(client)
    feed = connect(client, headers).json()
    internet.pages[LINK] = feed_fetch.FeedFetchError(
        "The calendar's website answered with error 500."
    )
    synced = client.post(f"{FEEDS}/{feed['id']}/sync", headers=headers).json()
    assert synced["last_error"] == "The calendar's website answered with error 500."
    assert synced["last_synced_at"] == feed["last_synced_at"]
    assert len([b for b in busy(client, headers) if b["source"] == "calendar"]) == 1


def test_stale_feeds_sync_when_asked_and_fresh_ones_do_not(
    client: TestClient, internet: FakeInternet
) -> None:
    internet.pages[LINK] = calendar(SHIFT)
    headers = new_user(client)
    connect(client, headers)
    internet.requests.clear()

    set_time(client, NOW + timedelta(hours=1))
    client.post(f"{FEEDS}/sync-stale", headers=headers)
    assert internet.requests == []

    set_time(client, NOW + timedelta(hours=7))
    client.post(f"{FEEDS}/sync-stale", headers=headers)
    assert len(internet.requests) == 1


def test_imported_blocks_are_read_only_and_not_in_the_manual_list(
    client: TestClient, internet: FakeInternet
) -> None:
    internet.pages[LINK] = calendar(SHIFT)
    headers = new_user(client)
    connect(client, headers)
    block = next(b for b in busy(client, headers) if b["source"] == "calendar")
    assert client.get(f"{API}/availability/one-off-blocks", headers=headers).json() == []
    body = {"title": "Mine now", "start_at": block["start_at"], "end_at": block["end_at"]}
    for response in (
        client.put(f"{API}/availability/one-off-blocks/{block['id']}", json=body, headers=headers),
        client.delete(f"{API}/availability/one-off-blocks/{block['id']}", headers=headers),
    ):
        assert response.status_code == 409
        assert response.json()["error"]["code"] == "imported_block"


def test_disconnecting_removes_its_busy_time(client: TestClient, internet: FakeInternet) -> None:
    internet.pages[LINK] = calendar(SHIFT, DUE)
    headers = new_user(client)
    feed = connect(client, headers).json()
    assert client.delete(f"{FEEDS}/{feed['id']}", headers=headers).status_code == 204
    assert busy(client, headers) == []
    assert client.get(SUGGESTIONS, headers=headers).json() == []


def test_renaming(client: TestClient, internet: FakeInternet) -> None:
    internet.pages[LINK] = calendar(SHIFT)
    headers = new_user(client)
    feed = connect(client, headers).json()
    renamed = client.patch(f"{FEEDS}/{feed['id']}", json={"name": "YorkU"}, headers=headers).json()
    assert renamed["name"] == "YorkU"


def test_feed_limit(client: TestClient, internet: FakeInternet) -> None:
    headers = new_user(client)
    for index in range(10):
        url = f"https://cal{index}.example.com/a.ics"
        internet.pages[url] = calendar(SHIFT)
        assert connect(client, headers, url).status_code == 201
    internet.pages["https://more.example.com/a.ics"] = calendar(SHIFT)
    assert (
        "up to 10"
        in field_errors(connect(client, headers, "https://more.example.com/a.ics"))["url"]
    )


def test_deadlines_become_suggestions_with_a_course_guess(
    client: TestClient, internet: FakeInternet
) -> None:
    headers = new_user(client)
    new_course(client, headers, name="Software Design", code="EECS 2030")
    new_course(client, headers, name="Other", code="EECS 20")
    internet.pages[LINK] = calendar(DUE, PAST_DUE)
    connect(client, headers)
    [suggestion] = client.get(SUGGESTIONS, headers=headers).json()
    assert suggestion["title"] == "Assignment 2 is due"
    assert suggestion["due_at"].startswith("2026-11-20T04:59")
    assert suggestion["course_name"] == "Software Design"
    assert suggestion["feed_name"] == "eClass"


def test_accepting_creates_the_task(client: TestClient, internet: FakeInternet) -> None:
    headers = new_user(client)
    course = new_course(client, headers, code="EECS2030")
    internet.pages[LINK] = calendar(DUE)
    feed = connect(client, headers).json()
    [suggestion] = client.get(SUGGESTIONS, headers=headers).json()

    response = client.post(
        f"{SUGGESTIONS}/{suggestion['id']}/accept",
        json={
            "estimated_minutes": 240,
            "course_id": course["id"],
            "title": "Assignment 2",
            "priority": 3,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    task = response.json()
    assert (task["title"], task["estimated_minutes"], task["priority"]) == ("Assignment 2", 240, 3)
    assert task["deadline_at"].startswith("2026-11-20T04:59")
    assert task["course_id"] == course["id"]
    assert client.get(SUGGESTIONS, headers=headers).json() == []

    # Syncing again does not bring an accepted deadline back.
    client.post(f"{FEEDS}/{feed['id']}/sync", headers=headers)
    assert client.get(SUGGESTIONS, headers=headers).json() == []
    again = client.post(
        f"{SUGGESTIONS}/{suggestion['id']}/accept", json={"estimated_minutes": 60}, headers=headers
    )
    assert again.json()["error"]["code"] == "suggestion_closed"


def test_accepting_into_another_students_course_is_refused(
    client: TestClient, internet: FakeInternet
) -> None:
    owner, other = new_user(client), new_user(client)
    foreign = new_course(client, other)
    internet.pages[LINK] = calendar(DUE)
    connect(client, owner)
    [suggestion] = client.get(SUGGESTIONS, headers=owner).json()
    response = client.post(
        f"{SUGGESTIONS}/{suggestion['id']}/accept",
        json={"estimated_minutes": 60, "course_id": foreign["id"]},
        headers=owner,
    )
    assert "course_id" in field_errors(response)
    assert len(client.get(SUGGESTIONS, headers=owner).json()) == 1


def test_dismissed_deadlines_stay_dismissed(client: TestClient, internet: FakeInternet) -> None:
    internet.pages[LINK] = calendar(DUE)
    headers = new_user(client)
    feed = connect(client, headers).json()
    [suggestion] = client.get(SUGGESTIONS, headers=headers).json()
    assert (
        client.post(f"{SUGGESTIONS}/{suggestion['id']}/dismiss", headers=headers).status_code == 204
    )
    client.post(f"{FEEDS}/{feed['id']}/sync", headers=headers)
    assert client.get(SUGGESTIONS, headers=headers).json() == []


def test_pending_deadlines_follow_their_event(client: TestClient, internet: FakeInternet) -> None:
    internet.pages[LINK] = calendar(DUE)
    headers = new_user(client)
    feed = connect(client, headers).json()
    internet.pages[LINK] = calendar(DUE.replace("20261120T045900Z", "20261122T045900Z"))
    client.post(f"{FEEDS}/{feed['id']}/sync", headers=headers)
    [moved] = client.get(SUGGESTIONS, headers=headers).json()
    assert moved["due_at"].startswith("2026-11-22")

    internet.pages[LINK] = calendar(SHIFT)
    client.post(f"{FEEDS}/{feed['id']}/sync", headers=headers)
    assert client.get(SUGGESTIONS, headers=headers).json() == []


def test_passed_deadlines_drop_out_of_the_list(client: TestClient, internet: FakeInternet) -> None:
    internet.pages[LINK] = calendar(DUE)
    headers = new_user(client)
    connect(client, headers)
    set_time(client, datetime(2026, 11, 21, tzinfo=UTC))
    assert client.get(SUGGESTIONS, headers=headers).json() == []


def test_busy_times_combine_every_source_with_categories(
    client: TestClient, internet: FakeInternet
) -> None:
    headers = new_user(client, "America/Toronto")
    client.post(
        f"{API}/availability/recurring-blocks",
        json={
            "title": "Lab",
            "category": "class",
            "day_of_week": 2,
            "start_minute": 600,
            "end_minute": 720,
        },
        headers=headers,
    )
    client.post(
        f"{API}/availability/one-off-blocks",
        json={
            "title": "Dinner with friends",
            "category": "social",
            "start_at": "2026-11-13T23:00:00Z",
            "end_at": "2026-11-14T02:00:00Z",
        },
        headers=headers,
    )
    internet.pages[LINK] = calendar(SHIFT)
    connect(client, headers)

    items = busy(client, headers, days=7)
    assert [(b["source"], b["title"], b["category"]) for b in items] == [
        ("calendar", "Work shift", "other"),
        ("weekly", "Lab", "class"),
        ("once", "Dinner with friends", "social"),
    ]
    # Wednesday 10:00 in Toronto, which is UTC-5 in November.
    assert items[1]["start_at"].startswith("2026-11-11T15:00")


def test_weekly_busy_times_keep_local_time_across_a_clock_change(client: TestClient) -> None:
    set_time(client, datetime(2026, 10, 26, tzinfo=UTC))
    headers = new_user(client, "America/Toronto")
    client.post(
        f"{API}/availability/recurring-blocks",
        json={
            "title": "Job",
            "category": "work",
            "day_of_week": 0,
            "start_minute": 540,
            "end_minute": 600,
        },
        headers=headers,
    )
    response = client.get(
        f"{API}/busy-times",
        params={"start": "2026-10-26T00:00:00Z", "end": "2026-11-09T00:00:00Z"},
        headers=headers,
    )
    assert [b["start_at"] for b in response.json()] == [
        "2026-10-26T13:00:00Z",
        "2026-11-02T14:00:00Z",
    ]


@pytest.mark.parametrize("days", [0, -1, 63])
def test_busy_range_is_bounded(client: TestClient, days: int) -> None:
    headers = new_user(client)
    response = client.get(
        f"{API}/busy-times",
        params={"start": NOW.isoformat(), "end": (NOW + timedelta(days=days)).isoformat()},
        headers=headers,
    )
    assert "end" in field_errors(response)


def test_categories_are_validated(client: TestClient) -> None:
    headers = new_user(client)
    response = client.post(
        f"{API}/availability/recurring-blocks",
        json={
            "title": "X",
            "category": "party",
            "day_of_week": 1,
            "start_minute": 0,
            "end_minute": 60,
        },
        headers=headers,
    )
    assert "category" in field_errors(response)


def test_blocks_without_a_category_default_to_other(client: TestClient) -> None:
    headers = new_user(client)
    response = client.post(
        f"{API}/availability/recurring-blocks",
        json={"title": "X", "day_of_week": 1, "start_minute": 0, "end_minute": 60},
        headers=headers,
    )
    assert response.json()["category"] == "other"


def test_busy_times_never_include_another_students(
    client: TestClient, internet: FakeInternet
) -> None:
    owner, other = new_user(client), new_user(client)
    client.post(
        f"{API}/availability/recurring-blocks",
        json={"title": "Lab", "day_of_week": 2, "start_minute": 600, "end_minute": 720},
        headers=owner,
    )
    client.post(
        f"{API}/availability/one-off-blocks",
        json={
            "title": "Party",
            "start_at": "2026-11-13T23:00:00Z",
            "end_at": "2026-11-14T02:00:00Z",
        },
        headers=owner,
    )
    internet.pages[LINK] = calendar(SHIFT)
    connect(client, owner)
    assert len(busy(client, owner)) == 4
    assert busy(client, other) == []


def test_decided_suggestions_keep_what_the_student_saw(
    client: TestClient, internet: FakeInternet, db: Any
) -> None:
    from app.models import DeadlineSuggestion

    internet.pages[LINK] = calendar(DUE)
    headers = new_user(client)
    feed = connect(client, headers).json()
    [suggestion] = client.get(SUGGESTIONS, headers=headers).json()
    client.post(f"{SUGGESTIONS}/{suggestion['id']}/dismiss", headers=headers)
    internet.pages[LINK] = calendar(DUE.replace("Assignment 2 is due", "Renamed"))
    client.post(f"{FEEDS}/{feed['id']}/sync", headers=headers)
    assert db.get(DeadlineSuggestion, suggestion["id"]).title == "Assignment 2 is due"

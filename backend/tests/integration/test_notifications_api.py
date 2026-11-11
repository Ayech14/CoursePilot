"""Notifications: what produces them, that they never repeat, and that a changed fact is new."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services.scheduling import utc_now
from tests.integration.helpers import API, Headers, new_task, new_user

NOW = datetime(2026, 2, 4, 15, 0, tzinfo=UTC)  # Wednesday, 10:00 AM in Toronto.
URL = f"{API}/notifications"


def set_time(client: TestClient, moment: datetime) -> None:
    client.app.dependency_overrides[utc_now] = lambda: moment  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def frozen_time(client: TestClient) -> Iterator[None]:
    set_time(client, NOW)
    yield


def feed(client: TestClient, headers: Headers) -> dict[str, Any]:
    response = client.get(URL, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def kinds(client: TestClient, headers: Headers) -> list[tuple[str, str]]:
    return sorted((n["kind"], n["title"]) for n in feed(client, headers)["items"])


def due(hours: float) -> str:
    return (NOW + timedelta(hours=hours)).isoformat()


def study_hours(client: TestClient, headers: Headers) -> None:
    windows = [{"day_of_week": d, "start_minute": 480, "end_minute": 1320} for d in range(7)]
    response = client.put(f"{API}/availability/windows", json={"windows": windows}, headers=headers)
    assert response.status_code == 200, response.text


def plan(client: TestClient, headers: Headers, task: str, start: datetime, minutes: int) -> str:
    response = client.post(
        f"{API}/sessions",
        json={
            "task_id": task,
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(minutes=minutes)).isoformat(),
            "acknowledge_warnings": True,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_a_new_student_has_none(client: TestClient) -> None:
    assert feed(client, new_user(client)) == {"items": [], "unread": 0}


def test_a_planned_task_due_within_two_days_is_approaching_in_the_students_words(
    client: TestClient,
) -> None:
    user = new_user(client)
    study_hours(client, user)
    task = new_task(client, user, title="Lab report", deadline_at=due(30), estimated_minutes=60)
    plan(client, user, task["id"], NOW + timedelta(hours=2), 60)

    [item] = [n for n in feed(client, user)["items"] if n["kind"] == "deadline_approaching"]
    assert item["title"] == "Lab report is due soon"
    # 21:00 UTC on Thursday is 4:00 PM in Toronto.
    assert item["body"] == "Due Thu, Feb 5 at 4:00 PM, with 1h of work left."
    assert item["task_id"] == task["id"]
    assert item["read_at"] is None


def test_asking_again_never_repeats_a_notification(client: TestClient) -> None:
    user = new_user(client)
    new_task(client, user, deadline_at=due(30))
    first = feed(client, user)
    for _ in range(3):
        again = feed(client, user)
    assert again == first
    assert first["unread"] == len(first["items"]) > 0


def test_a_changed_deadline_is_a_new_event(client: TestClient) -> None:
    user = new_user(client)
    study_hours(client, user)
    task = new_task(client, user, title="Essay", deadline_at=due(30), estimated_minutes=30)
    plan(client, user, task["id"], NOW + timedelta(hours=2), 30)
    feed(client, user)
    client.patch(f"{API}/tasks/{task['id']}", json={"deadline_at": due(40)}, headers=user)
    titles = [n["title"] for n in feed(client, user)["items"]]
    assert titles.count("Essay is due soon") == 2


def test_a_passed_deadline_is_overdue_and_a_finished_task_is_not(client: TestClient) -> None:
    user = new_user(client)
    late = new_task(client, user, title="Quiz prep", deadline_at=due(3))
    done = new_task(client, user, title="Reading", deadline_at=due(3))
    client.patch(f"{API}/tasks/{done['id']}", json={"status": "completed"}, headers=user)

    set_time(client, NOW + timedelta(hours=5))
    overdue = [n for n in feed(client, user)["items"] if n["kind"] == "task_overdue"]
    assert [(n["title"], n["task_id"]) for n in overdue] == [("Quiz prep is overdue", late["id"])]
    assert "due Wed, Feb 4 at 1:00 PM" in overdue[0]["body"]


def test_work_that_does_not_fit_is_reported_per_task_when_there_are_study_hours(
    client: TestClient,
) -> None:
    user = new_user(client)
    study_hours(client, user)
    new_task(client, user, title="Project", deadline_at=due(24 * 5), estimated_minutes=300)
    [item] = [n for n in feed(client, user)["items"] if n["kind"] == "workload_conflict"]
    assert item["title"] == "Not enough time planned for Project"
    assert item["body"].startswith("5h of work is not in your schedule before it is due Mon, Feb 9")


def test_without_study_hours_one_notification_names_the_cause(client: TestClient) -> None:
    user = new_user(client)
    for title in ("Midterm", "Lab", "Essay"):
        new_task(client, user, title=title, deadline_at=due(24 * 5))
    conflicts = [n for n in feed(client, user)["items"] if n["kind"] == "workload_conflict"]
    assert [(n["title"], n["task_id"]) for n in conflicts] == [
        ("Nothing can be scheduled yet", None)
    ]
    assert conflicts[0]["body"].startswith("3 tasks need study time")


def test_a_missed_session_is_reported_once_and_suggests_an_update(client: TestClient) -> None:
    user = new_user(client)
    study_hours(client, user)
    task = new_task(
        client, user, title="Problem set", deadline_at=due(24 * 6), estimated_minutes=60
    )
    plan(client, user, task["id"], NOW + timedelta(hours=1), 60)
    feed(client, user)

    set_time(client, NOW + timedelta(hours=4))
    items = feed(client, user)["items"]
    [missed] = [n for n in items if n["kind"] == "task_unfinished"]
    assert missed["title"] == "Missed session for Problem set"
    assert "Wed, Feb 4 at 11:00 AM was not started" in missed["body"]
    [update] = [n for n in items if n["kind"] == "schedule_adjusted"]
    assert update["body"].startswith("1 missed session and ")
    assert feed(client, user)["items"] == items


def test_reading_one_and_reading_all(client: TestClient) -> None:
    user = new_user(client)
    for title in ("A", "B"):
        new_task(client, user, title=title, deadline_at=due(3))
    set_time(client, NOW + timedelta(hours=4))
    items = feed(client, user)["items"]
    assert len(items) >= 2

    response = client.post(f"{URL}/{items[0]['id']}/read", headers=user)
    assert response.status_code == 200
    assert response.json()["read_at"] == (NOW + timedelta(hours=4)).isoformat().replace(
        "+00:00", "Z"
    )
    assert feed(client, user)["unread"] == len(items) - 1

    assert client.post(f"{URL}/read-all", headers=user).status_code == 204
    assert feed(client, user)["unread"] == 0


def test_reading_an_unknown_notification_is_not_found(client: TestClient) -> None:
    response = client.post(
        f"{URL}/01a1c6ed-53bc-7702-ab84-a40687b982cf/read", headers=new_user(client)
    )
    assert response.status_code == 404

from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.models.enums import TaskType
from tests.integration.helpers import (
    API,
    DEADLINE,
    Headers,
    field_errors,
    new_course,
    new_task,
    new_user,
    task_body,
)


def patch_task(client: TestClient, headers: Headers, task: dict[str, Any], **body: Any) -> Any:
    return client.patch(f"{API}/tasks/{task['id']}", json=body, headers=headers)


def post_progress(client: TestClient, headers: Headers, task: dict[str, Any], **body: Any) -> Any:
    return client.post(f"{API}/tasks/{task['id']}/progress", json=body, headers=headers)


# --- Creating -------------------------------------------------------------------------------


def test_new_task_starts_with_remaining_equal_to_estimate(client: TestClient) -> None:
    task = new_task(client, new_user(client), estimated_minutes=90)
    assert task["remaining_minutes"] == 90
    assert task["actual_minutes"] == 0
    assert task["status"] == "todo"
    assert task["priority"] == 2
    assert task["completed_at"] is None


@pytest.mark.parametrize("task_type", list(TaskType))
def test_every_task_type_can_be_created(client: TestClient, task_type: TaskType) -> None:
    assert new_task(client, new_user(client), task_type=task_type)["task_type"] == task_type


def test_deadline_keeps_the_same_instant(client: TestClient) -> None:
    task = new_task(client, new_user(client), deadline_at=DEADLINE)
    assert datetime.fromisoformat(task["deadline_at"]) == datetime.fromisoformat(DEADLINE)


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"title": "   "}, "title"),
        ({"title": "x" * 201}, "title"),
        ({"task_type": "party"}, "task_type"),
        ({"estimated_minutes": 0}, "estimated_minutes"),
        ({"estimated_minutes": 30_001}, "estimated_minutes"),
        ({"estimated_minutes": "soon"}, "estimated_minutes"),
        ({"remaining_minutes": 0}, "remaining_minutes"),
        ({"priority": 0}, "priority"),
        ({"priority": 5}, "priority"),
        ({"deadline_at": "2026-12-01T23:59:00"}, "deadline_at"),
        ({"deadline_at": "next week"}, "deadline_at"),
    ],
)
def test_invalid_task_rejected(client: TestClient, overrides: dict[str, Any], field: str) -> None:
    response = client.post(f"{API}/tasks", json=task_body(**overrides), headers=new_user(client))
    assert list(field_errors(response)) == [field]


@pytest.mark.parametrize("task_type", ["midterm", "final_exam", "quiz"])
def test_exams_require_a_date(client: TestClient, task_type: str) -> None:
    response = client.post(
        f"{API}/tasks",
        json=task_body(task_type=task_type, deadline_at=None),
        headers=new_user(client),
    )
    assert list(field_errors(response)) == ["deadline_at"]


def test_exam_date_cannot_be_cleared_later(client: TestClient) -> None:
    headers = new_user(client)
    exam = new_task(client, headers, task_type="midterm")
    assert list(field_errors(patch_task(client, headers, exam, deadline_at=None))) == [
        "deadline_at"
    ]


def test_task_without_deadline_or_course_allowed(client: TestClient) -> None:
    task = new_task(client, new_user(client), task_type="reading", deadline_at=None)
    assert task["deadline_at"] is None
    assert task["course_id"] is None


def test_unknown_course_is_a_field_error(client: TestClient) -> None:
    response = client.post(
        f"{API}/tasks",
        json=task_body(course_id="0190a000-0000-7000-8000-000000000001"),
        headers=new_user(client),
    )
    assert list(field_errors(response)) == ["course_id"]


def test_cannot_add_task_to_archived_course(client: TestClient) -> None:
    headers = new_user(client)
    course = new_course(client, headers)
    client.patch(f"{API}/courses/{course['id']}", json={"archived": True}, headers=headers)

    response = client.post(f"{API}/tasks", json=task_body(course_id=course["id"]), headers=headers)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "course_archived"


# --- Listing --------------------------------------------------------------------------------


def titles(client: TestClient, headers: Headers, **params: Any) -> list[str]:
    response = client.get(f"{API}/tasks", params=params, headers=headers)
    assert response.status_code == 200, response.text
    return [task["title"] for task in response.json()["items"]]


def test_sorted_by_deadline_with_undated_last(client: TestClient) -> None:
    headers = new_user(client)
    new_task(client, headers, title="Undated", task_type="reading", deadline_at=None)
    new_task(client, headers, title="Later", deadline_at="2099-02-01T00:00Z")
    new_task(client, headers, title="Soon", deadline_at="2099-01-01T00:00Z")
    assert titles(client, headers) == ["Soon", "Later", "Undated"]


def test_filters(client: TestClient) -> None:
    headers = new_user(client)
    course = new_course(client, headers)
    new_task(client, headers, title="A", course_id=course["id"], deadline_at="2099-01-01T00:00Z")
    new_task(client, headers, title="B", task_type="quiz", deadline_at="2099-03-01T00:00Z")
    done = new_task(client, headers, title="C", deadline_at="2099-05-01T00:00Z")
    patch_task(client, headers, done, status="completed")

    assert titles(client, headers, course_id=course["id"]) == ["A"]
    assert titles(client, headers, task_type="quiz") == ["B"]
    assert titles(client, headers, status=["completed"]) == ["C"]
    assert titles(client, headers, status=["todo", "completed"]) == ["A", "B", "C"]
    assert titles(client, headers, due_after="2099-02-01T00:00Z") == ["B", "C"]
    assert titles(client, headers, due_before="2099-02-01T00:00Z") == ["A"]


def test_invalid_filter_rejected(client: TestClient) -> None:
    response = client.get(f"{API}/tasks", params={"status": "nope"}, headers=new_user(client))
    assert response.status_code == 422


def test_pagination_reports_total(client: TestClient) -> None:
    headers = new_user(client)
    for index in range(3):
        new_task(client, headers, title=f"T{index}", deadline_at=f"2099-01-0{index + 1}T00:00Z")

    page = client.get(f"{API}/tasks", params={"limit": 2, "offset": 1}, headers=headers).json()

    assert page["total"] == 3
    assert [task["title"] for task in page["items"]] == ["T1", "T2"]


# --- Updating and status --------------------------------------------------------------------


def test_partial_update(client: TestClient) -> None:
    headers = new_user(client)
    task = new_task(client, headers, description="Keep")

    updated = patch_task(client, headers, task, title="New title", priority=4).json()

    assert (updated["title"], updated["priority"]) == ("New title", 4)
    assert updated["description"] == "Keep"
    assert updated["estimated_minutes"] == task["estimated_minutes"]


def test_required_field_cannot_be_null(client: TestClient) -> None:
    headers = new_user(client)
    task = new_task(client, headers)
    assert list(field_errors(patch_task(client, headers, task, title=None))) == ["title"]


def test_course_can_be_cleared(client: TestClient) -> None:
    headers = new_user(client)
    task = new_task(client, headers, course_id=new_course(client, headers)["id"])
    assert patch_task(client, headers, task, course_id=None).json()["course_id"] is None


def test_remaining_may_exceed_estimate_when_task_runs_long(client: TestClient) -> None:
    headers = new_user(client)
    task = new_task(client, headers, estimated_minutes=60)
    assert (
        patch_task(client, headers, task, remaining_minutes=200).json()["remaining_minutes"] == 200
    )


def test_completing_clears_remaining_and_sets_timestamp(client: TestClient) -> None:
    headers = new_user(client)
    done = patch_task(client, headers, new_task(client, headers), status="completed").json()
    assert done["status"] == "completed"
    assert done["remaining_minutes"] == 0
    assert done["completed_at"] is not None


def test_setting_remaining_to_zero_completes_the_task(client: TestClient) -> None:
    headers = new_user(client)
    done = patch_task(client, headers, new_task(client, headers), remaining_minutes=0).json()
    assert done["status"] == "completed"
    assert done["completed_at"] is not None


def test_reopening_estimates_what_is_left(client: TestClient) -> None:
    headers = new_user(client)
    task = new_task(client, headers, estimated_minutes=120)
    post_progress(client, headers, task, minutes_spent=50, mark_completed=True)

    reopened = patch_task(client, headers, task, status="in_progress").json()

    assert reopened["status"] == "in_progress"
    assert reopened["remaining_minutes"] == 70
    assert reopened["completed_at"] is None


def test_reopening_an_overrun_task_keeps_some_work_remaining(client: TestClient) -> None:
    headers = new_user(client)
    task = new_task(client, headers, estimated_minutes=60)
    post_progress(client, headers, task, minutes_spent=90, mark_completed=True)

    assert patch_task(client, headers, task, status="todo").json()["remaining_minutes"] == 15


def test_setting_remaining_on_completed_task_reopens_it(client: TestClient) -> None:
    headers = new_user(client)
    task = new_task(client, headers)
    patch_task(client, headers, task, status="completed")

    reopened = patch_task(client, headers, task, remaining_minutes=30).json()

    assert reopened["remaining_minutes"] == 30
    assert reopened["status"] == "todo"
    assert reopened["completed_at"] is None


@pytest.mark.parametrize(
    "body",
    [{"status": "completed", "remaining_minutes": 30}, {"status": "todo", "remaining_minutes": 0}],
)
def test_contradictory_status_and_remaining_rejected(
    client: TestClient, body: dict[str, Any]
) -> None:
    headers = new_user(client)
    response = patch_task(client, headers, new_task(client, headers), **body)
    assert list(field_errors(response)) == ["remaining_minutes"]


# --- Progress -------------------------------------------------------------------------------


def test_logging_time_reduces_remaining_and_starts_task(client: TestClient) -> None:
    headers = new_user(client)
    task = post_progress(client, headers, new_task(client, headers), minutes_spent=30).json()
    assert task["actual_minutes"] == 30
    assert task["remaining_minutes"] == 90
    assert task["status"] == "in_progress"


def test_logged_time_accumulates(client: TestClient) -> None:
    headers = new_user(client)
    task = new_task(client, headers)
    post_progress(client, headers, task, minutes_spent=30)
    assert post_progress(client, headers, task, minutes_spent=20).json()["actual_minutes"] == 50


def test_spending_the_whole_estimate_does_not_finish_the_task(client: TestClient) -> None:
    headers = new_user(client)
    task = new_task(client, headers, estimated_minutes=60)

    updated = post_progress(client, headers, task, minutes_spent=60).json()

    assert updated["status"] == "in_progress"
    assert updated["remaining_minutes"] == 15


def test_explicit_remaining_overrides_the_calculation(client: TestClient) -> None:
    headers = new_user(client)
    updated = post_progress(
        client, headers, new_task(client, headers), minutes_spent=30, remaining_minutes=300
    ).json()
    assert updated["actual_minutes"] == 30
    assert updated["remaining_minutes"] == 300


def test_mark_completed_records_time_and_finishes(client: TestClient) -> None:
    headers = new_user(client)
    updated = post_progress(
        client, headers, new_task(client, headers), minutes_spent=45, mark_completed=True
    ).json()
    assert updated["status"] == "completed"
    assert updated["actual_minutes"] == 45
    assert updated["remaining_minutes"] == 0


def test_empty_progress_rejected(client: TestClient) -> None:
    headers = new_user(client)
    response = post_progress(client, headers, new_task(client, headers))
    assert list(field_errors(response)) == ["minutes_spent"]


@pytest.mark.parametrize("minutes", [0, -5, 1441])
def test_invalid_minutes_rejected(client: TestClient, minutes: int) -> None:
    headers = new_user(client)
    response = post_progress(client, headers, new_task(client, headers), minutes_spent=minutes)
    assert list(field_errors(response)) == ["minutes_spent"]


def test_progress_on_completed_task_conflicts(client: TestClient) -> None:
    headers = new_user(client)
    task = new_task(client, headers)
    patch_task(client, headers, task, status="completed")

    response = post_progress(client, headers, task, minutes_spent=10)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "task_completed"


def test_delete_task(client: TestClient) -> None:
    headers = new_user(client)
    task = new_task(client, headers)
    assert client.delete(f"{API}/tasks/{task['id']}", headers=headers).status_code == 204
    assert client.get(f"{API}/tasks/{task['id']}", headers=headers).status_code == 404

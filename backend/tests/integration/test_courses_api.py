from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.helpers import API, field_errors, new_course, new_task, new_user


def test_create_course_normalizes_input(client: TestClient) -> None:
    headers = new_user(client)
    body = {
        "name": "  Data Structures ",
        "code": " EECS2101 ",
        "description": "Trees and graphs",
        "color": "#AABBCC",
    }

    course = client.post(f"{API}/courses", json=body, headers=headers).json()

    assert course["name"] == "Data Structures"
    assert course["code"] == "EECS2101"
    assert course["color"] == "#aabbcc"
    assert course["archived_at"] is None
    assert course["progress"]["total_tasks"] == 0


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"name": "", "color": "#112233"}, "name"),
        ({"name": "x" * 121, "color": "#112233"}, "name"),
        ({"name": "Math", "color": "red"}, "color"),
        ({"name": "Math"}, "color"),
        ({"color": "#112233"}, "name"),
        ({"name": "Math", "color": "#112233", "code": "x" * 33}, "code"),
    ],
)
def test_invalid_course_rejected(client: TestClient, body: dict[str, Any], field: str) -> None:
    response = client.post(f"{API}/courses", json=body, headers=new_user(client))
    assert list(field_errors(response)) == [field]


def test_list_is_sorted_and_hides_archived_by_default(client: TestClient) -> None:
    headers = new_user(client)
    new_course(client, headers, name="Zoology")
    new_course(client, headers, name="Art")
    archived = new_course(client, headers, name="Old")
    client.patch(f"{API}/courses/{archived['id']}", json={"archived": True}, headers=headers)

    names = [c["name"] for c in client.get(f"{API}/courses", headers=headers).json()]
    with_archived = client.get(
        f"{API}/courses", params={"include_archived": True}, headers=headers
    ).json()

    assert names == ["Art", "Zoology"]
    assert [c["name"] for c in with_archived] == ["Art", "Old", "Zoology"]


def test_partial_update_changes_only_sent_fields(client: TestClient) -> None:
    headers = new_user(client)
    course = new_course(client, headers, code="EECS1", description="Keep me")

    updated = client.patch(
        f"{API}/courses/{course['id']}", json={"name": "Renamed"}, headers=headers
    ).json()

    assert updated["name"] == "Renamed"
    assert updated["code"] == "EECS1"
    assert updated["description"] == "Keep me"


def test_nullable_field_can_be_cleared_but_required_field_cannot(client: TestClient) -> None:
    headers = new_user(client)
    course = new_course(client, headers, code="EECS1")
    url = f"{API}/courses/{course['id']}"

    assert client.patch(url, json={"code": None}, headers=headers).json()["code"] is None
    assert list(field_errors(client.patch(url, json={"name": None}, headers=headers))) == ["name"]


def test_archive_and_restore(client: TestClient) -> None:
    headers = new_user(client)
    url = f"{API}/courses/{new_course(client, headers)['id']}"

    assert client.patch(url, json={"archived": True}, headers=headers).json()["archived_at"]
    assert (
        client.patch(url, json={"archived": False}, headers=headers).json()["archived_at"] is None
    )


def test_progress_aggregates_only_that_course(client: TestClient) -> None:
    headers = new_user(client)
    course = new_course(client, headers)
    other = new_course(client, headers, name="Other")
    done = new_task(client, headers, course_id=course["id"], estimated_minutes=60)
    client.post(
        f"{API}/tasks/{done['id']}/progress",
        json={"minutes_spent": 45, "mark_completed": True},
        headers=headers,
    )
    new_task(client, headers, course_id=course["id"], estimated_minutes=100)
    new_task(client, headers, course_id=other["id"], estimated_minutes=999)
    new_task(client, headers, estimated_minutes=999)

    progress = client.get(f"{API}/courses/{course['id']}", headers=headers).json()["progress"]

    assert progress["total_tasks"] == 2
    assert progress["completed_tasks"] == 1
    assert progress["estimated_minutes"] == 160
    assert progress["remaining_minutes"] == 100
    assert progress["actual_minutes"] == 45


def test_next_deadline_ignores_completed_and_past_tasks(client: TestClient) -> None:
    headers = new_user(client)
    course = new_course(client, headers)
    finished = new_task(client, headers, course_id=course["id"], deadline_at="2099-01-01T00:00:00Z")
    client.patch(f"{API}/tasks/{finished['id']}", json={"status": "completed"}, headers=headers)
    new_task(client, headers, course_id=course["id"], deadline_at="2020-01-01T00:00:00Z")
    new_task(client, headers, course_id=course["id"], deadline_at="2099-06-01T00:00:00Z")

    listed = client.get(f"{API}/courses", headers=headers).json()[0]

    assert listed["progress"]["next_deadline_at"].startswith("2099-06-01")


def test_detail_lists_open_dated_tasks_in_deadline_order(client: TestClient) -> None:
    headers = new_user(client)
    course = new_course(client, headers)
    new_task(
        client, headers, course_id=course["id"], title="Later", deadline_at="2099-02-01T00:00Z"
    )
    new_task(client, headers, course_id=course["id"], title="Soon", deadline_at="2099-01-01T00:00Z")
    new_task(
        client,
        headers,
        course_id=course["id"],
        title="Undated",
        task_type="reading",
        deadline_at=None,
    )

    detail = client.get(f"{API}/courses/{course['id']}", headers=headers).json()

    assert [t["title"] for t in detail["upcoming_tasks"]] == ["Soon", "Later"]


def test_delete_course_removes_its_tasks(client: TestClient) -> None:
    headers = new_user(client)
    course = new_course(client, headers)
    task = new_task(client, headers, course_id=course["id"])

    response = client.delete(f"{API}/courses/{course['id']}", headers=headers)

    assert response.status_code == 204
    assert client.get(f"{API}/courses/{course['id']}", headers=headers).status_code == 404
    assert client.get(f"{API}/tasks/{task['id']}", headers=headers).status_code == 404

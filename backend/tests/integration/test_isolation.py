"""Proves that accounts cannot reach each other's data.

The route lists come from the application itself, so a new endpoint fails these tests until it
is covered. Forgetting to protect or check a route cannot go unnoticed.
"""

import re
import uuid
from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.integration.helpers import (
    API,
    Headers,
    field_errors,
    new_course,
    new_task,
    new_user,
    task_body,
)

PUBLIC_ROUTES = {
    ("POST", f"{API}/auth/register"),
    ("POST", f"{API}/auth/login"),
    ("POST", f"{API}/auth/refresh"),
    ("POST", f"{API}/auth/logout"),
}

_RECURRING_BODY = {"title": "Lab", "day_of_week": 1, "start_minute": 600, "end_minute": 660}
_ONE_OFF_BODY = {
    "title": "Trip",
    "start_at": "2026-12-24T09:00:00Z",
    "end_at": "2026-12-25T09:00:00Z",
}

# Every route that addresses one record by ID, with a valid body, as attempted by the wrong user.
ID_ROUTES: dict[tuple[str, str], dict[str, Any] | None] = {
    ("GET", "/courses/{course_id}"): None,
    ("PATCH", "/courses/{course_id}"): {"name": "Hijacked"},
    ("DELETE", "/courses/{course_id}"): None,
    ("GET", "/tasks/{task_id}"): None,
    ("PATCH", "/tasks/{task_id}"): {"title": "Hijacked"},
    ("POST", "/tasks/{task_id}/progress"): {"minutes_spent": 5},
    ("DELETE", "/tasks/{task_id}"): None,
    ("PUT", "/availability/recurring-blocks/{block_id}"): _RECURRING_BODY,
    ("DELETE", "/availability/recurring-blocks/{block_id}"): None,
    ("PUT", "/availability/one-off-blocks/{block_id}"): _ONE_OFF_BODY,
    ("DELETE", "/availability/one-off-blocks/{block_id}"): None,
    ("GET", "/schedule/proposals/{proposal_id}"): None,
    ("POST", "/schedule/proposals/{proposal_id}/apply"): None,
    ("POST", "/schedule/proposals/{proposal_id}/reject"): None,
}


def all_routes() -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, operations in create_app().openapi()["paths"].items()
        if path.startswith(API)
        for method in operations
    }


@pytest.mark.parametrize(("method", "path"), sorted(all_routes() - PUBLIC_ROUTES))
def test_every_private_route_requires_authentication(
    client: TestClient, method: str, path: str
) -> None:
    url = re.sub(r"{\w+}", str(uuid.uuid4()), path)
    response = client.request(method, url)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


def test_isolation_table_covers_every_route_with_an_id() -> None:
    with_ids = {(m, p.removeprefix(API)) for m, p in all_routes() if "{" in p}
    assert with_ids == set(ID_ROUTES)


def _seed(client: TestClient, owner: Headers) -> dict[str, tuple[str, str]]:
    """Create one of each record; return its ID and the URL that proves it is unchanged."""
    course = new_course(client, owner)["id"]
    task = new_task(client, owner, course_id=course)["id"]
    recurring = client.post(
        f"{API}/availability/recurring-blocks", json=_RECURRING_BODY, headers=owner
    ).json()["id"]
    one_off = client.post(
        f"{API}/availability/one-off-blocks", json=_ONE_OFF_BODY, headers=owner
    ).json()["id"]
    proposal = client.post(f"{API}/schedule/preview", headers=owner).json()["id"]
    return {
        "proposal_id": (proposal, f"{API}/schedule/proposals/{proposal}"),
        "course_id": (course, f"{API}/courses/{course}"),
        "task_id": (task, f"{API}/tasks/{task}"),
        "/recurring-blocks": (recurring, f"{API}/availability/recurring-blocks"),
        "/one-off-blocks": (one_off, f"{API}/availability/one-off-blocks"),
    }


@pytest.mark.parametrize(("method", "path"), sorted(ID_ROUTES), ids=lambda value: value)
def test_other_users_records_look_nonexistent_and_stay_unchanged(
    client: TestClient, method: str, path: str
) -> None:
    owner, intruder = new_user(client), new_user(client)
    seeded = _seed(client, owner)
    key = next(k for k in seeded if k in path)
    record_id, check_url = seeded[key]
    before = client.get(check_url, headers=owner).json()

    url = API + re.sub(r"{\w+}", record_id, path)
    response = client.request(method, url, json=ID_ROUTES[(method, path)], headers=intruder)

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert client.get(check_url, headers=owner).json() == before


ListRequest = Callable[[TestClient, Headers], list[Any]]

LISTS: dict[str, ListRequest] = {
    "courses": lambda c, h: c.get(f"{API}/courses", headers=h).json(),
    "tasks": lambda c, h: c.get(f"{API}/tasks", headers=h).json()["items"],
    "recurring": lambda c, h: c.get(f"{API}/availability/recurring-blocks", headers=h).json(),
    "one_off": lambda c, h: c.get(f"{API}/availability/one-off-blocks", headers=h).json(),
}


@pytest.mark.parametrize("name", sorted(LISTS))
def test_lists_contain_only_the_callers_records(client: TestClient, name: str) -> None:
    owner, other = new_user(client), new_user(client)
    _seed(client, owner)
    assert len(LISTS[name](client, owner)) == 1
    assert LISTS[name](client, other) == []


def test_weekly_windows_are_per_user(client: TestClient) -> None:
    owner, other = new_user(client), new_user(client)
    window = {"day_of_week": 0, "start_minute": 540, "end_minute": 600}
    client.put(f"{API}/availability/windows", json={"windows": [window]}, headers=owner)
    client.put(f"{API}/availability/windows", json={"windows": []}, headers=other)
    assert len(client.get(f"{API}/availability/windows", headers=owner).json()) == 1


def test_preferences_are_per_user(client: TestClient) -> None:
    owner, other = new_user(client), new_user(client)
    body = client.get(f"{API}/preferences", headers=owner).json() | {"break_minutes": 33}
    client.put(f"{API}/preferences", json=body, headers=owner)
    assert client.get(f"{API}/preferences", headers=other).json()["break_minutes"] == 10


def test_cannot_create_task_in_another_users_course(client: TestClient) -> None:
    owner, intruder = new_user(client), new_user(client)
    course = new_course(client, owner)["id"]
    response = client.post(f"{API}/tasks", json=task_body(course_id=course), headers=intruder)
    assert list(field_errors(response)) == ["course_id"]


def test_cannot_move_own_task_into_another_users_course(client: TestClient) -> None:
    owner, intruder = new_user(client), new_user(client)
    course = new_course(client, owner)["id"]
    task = new_task(client, intruder)["id"]
    response = client.patch(f"{API}/tasks/{task}", json={"course_id": course}, headers=intruder)
    assert list(field_errors(response)) == ["course_id"]


def test_filtering_by_another_users_course_finds_nothing(client: TestClient) -> None:
    owner, intruder = new_user(client), new_user(client)
    course = new_course(client, owner)["id"]
    new_task(client, owner, course_id=course)
    page = client.get(f"{API}/tasks", params={"course_id": course}, headers=intruder).json()
    assert page == {"items": [], "total": 0}


def test_course_progress_excludes_other_users(client: TestClient) -> None:
    first, second = new_user(client), new_user(client)
    course = new_course(client, first)
    new_task(client, first, course_id=course["id"])
    new_course(client, second)
    new_task(client, second)
    assert client.get(f"{API}/courses", headers=second).json()[0]["progress"]["total_tasks"] == 0

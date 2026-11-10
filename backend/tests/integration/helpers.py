"""Small API helpers shared by integration tests."""

import uuid
from typing import Any

from fastapi.testclient import TestClient

Headers = dict[str, str]
API = "/api/v1"
DEADLINE = "2026-12-01T23:59:00-05:00"


def new_user(client: TestClient, timezone: str = "America/Toronto") -> Headers:
    response = client.post(
        f"{API}/auth/register",
        json={
            "email": f"{uuid.uuid4().hex}@example.com",
            "password": "a-long-enough-password",
            "display_name": "Student",
            "timezone": timezone,
        },
    )
    assert response.status_code == 201
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def new_course(client: TestClient, headers: Headers, **overrides: Any) -> dict[str, Any]:
    body = {"name": "Algorithms", "color": "#4F46E5"} | overrides
    response = client.post(f"{API}/courses", json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def task_body(**overrides: Any) -> dict[str, Any]:
    return {
        "title": "Problem set 1",
        "task_type": "assignment",
        "deadline_at": DEADLINE,
        "estimated_minutes": 120,
    } | overrides


def new_task(client: TestClient, headers: Headers, **overrides: Any) -> dict[str, Any]:
    response = client.post(f"{API}/tasks", json=task_body(**overrides), headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def field_errors(response: Any) -> dict[str, str]:
    assert response.status_code == 422, response.text
    return {item["field"]: item["message"] for item in response.json()["error"]["details"]}

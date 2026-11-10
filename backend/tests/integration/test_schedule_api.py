"""The scheduling workflow through the API, against real PostgreSQL."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import StudySession
from app.models.enums import SessionOrigin, SessionStatus
from app.services.scheduling import utc_now
from tests.integration.helpers import API, Headers, new_course, new_task, new_user

# A Monday morning, fixed so that every schedule in this file is exactly reproducible.
NOW = datetime(2026, 2, 2, 5, 0, tzinfo=UTC)
PREVIEW = f"{API}/schedule/preview"
DUE = "2026-02-06T23:00:00Z"


@pytest.fixture(autouse=True)
def frozen_time(client: TestClient) -> Iterator[None]:
    client.app.dependency_overrides[utc_now] = lambda: NOW  # type: ignore[attr-defined]
    yield


def set_hours(
    client: TestClient, headers: Headers, start: int = 540, end: int = 1020, days: int = 7
) -> None:
    windows = [
        {"day_of_week": day, "start_minute": start, "end_minute": end} for day in range(days)
    ]
    response = client.put(f"{API}/availability/windows", json={"windows": windows}, headers=headers)
    assert response.status_code == 200


def preview(client: TestClient, headers: Headers) -> dict[str, Any]:
    response = client.post(PREVIEW, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def apply(client: TestClient, headers: Headers, proposal: dict[str, Any]) -> Any:
    return client.post(f"{API}/schedule/proposals/{proposal['id']}/apply", headers=headers)


def sessions(client: TestClient, headers: Headers) -> list[dict[str, Any]]:
    return client.get(f"{API}/sessions", headers=headers).json()


def scheduled_user(client: TestClient, **task: Any) -> tuple[Headers, dict[str, Any]]:
    """A student with weekly hours, one task and an applied schedule."""
    headers = new_user(client, "UTC")
    set_hours(client, headers)
    created = new_task(client, headers, deadline_at=DUE, **task)
    assert apply(client, headers, preview(client, headers)).status_code == 200
    return headers, created


def stored_sessions(db: Session) -> list[StudySession]:
    return list(db.scalars(select(StudySession).order_by(StudySession.start_at)))


# --- Preview --------------------------------------------------------------------------------


def test_preview_describes_new_sessions_with_reasons(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    set_hours(client, headers)
    course = new_course(client, headers)
    task = new_task(client, headers, course_id=course["id"], deadline_at=DUE, estimated_minutes=100)

    proposal = preview(client, headers)

    assert proposal["status"] == "pending"
    assert proposal["trigger"] == "generate"
    assert proposal["at_risk"] == []
    assert len(proposal["changes"]) == 2
    change = proposal["changes"][0]
    assert change["action"] == "create"
    assert change["task_id"] == task["id"]
    assert change["task_title"] == task["title"]
    assert change["course_color"] == course["color"]
    assert change["explanation"].endswith(".")


def test_preview_does_not_touch_the_real_schedule(client: TestClient, db: Session) -> None:
    headers = new_user(client, "UTC")
    set_hours(client, headers)
    new_task(client, headers, deadline_at=DUE)
    preview(client, headers)
    assert stored_sessions(db) == []


def test_current_proposal_is_available_later(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    created = preview(client, headers)
    current = client.get(f"{API}/schedule/proposals/current", headers=headers).json()
    assert current["id"] == created["id"]


def test_no_current_proposal_returns_null(client: TestClient) -> None:
    response = client.get(f"{API}/schedule/proposals/current", headers=new_user(client))
    assert response.status_code == 200
    assert response.json() is None


def test_new_preview_replaces_the_previous_one(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    first, second = preview(client, headers), preview(client, headers)

    response = apply(client, headers, first)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "proposal_closed"
    assert (
        client.get(f"{API}/schedule/proposals/current", headers=headers).json()["id"]
        == second["id"]
    )


def test_previews_are_reproducible(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    set_hours(client, headers)
    new_task(client, headers, deadline_at=DUE)

    def times(proposal: dict[str, Any]) -> list[str]:
        return [change["after_start_at"] for change in proposal["changes"]]

    assert times(preview(client, headers)) == times(preview(client, headers))


def test_weekly_hours_are_read_in_the_students_time_zone(client: TestClient) -> None:
    headers = new_user(client, "Asia/Tokyo")
    set_hours(client, headers, start=540, end=600)
    new_task(client, headers, deadline_at=DUE, estimated_minutes=50)

    start = preview(client, headers)["changes"][0]["after_start_at"]

    local = datetime.fromisoformat(start).astimezone(ZoneInfo("Asia/Tokyo"))
    assert (local.hour, local.minute) == (9, 0)


def test_completed_tasks_are_not_planned(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    set_hours(client, headers)
    task = new_task(client, headers, deadline_at=DUE)
    client.patch(f"{API}/tasks/{task['id']}", json={"status": "completed"}, headers=headers)
    assert preview(client, headers)["changes"] == []


def test_tasks_in_archived_courses_are_not_planned(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    set_hours(client, headers)
    course = new_course(client, headers)
    new_task(client, headers, course_id=course["id"], deadline_at=DUE)
    client.patch(f"{API}/courses/{course['id']}", json={"archived": True}, headers=headers)
    assert preview(client, headers)["changes"] == []


def test_preferences_shape_the_plan(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    set_hours(client, headers)
    new_task(client, headers, deadline_at=DUE, estimated_minutes=60)
    current = client.get(f"{API}/preferences", headers=headers).json()
    client.put(
        f"{API}/preferences",
        json=current | {"preferred_session_minutes": 30, "min_session_minutes": 15},
        headers=headers,
    )
    assert len(preview(client, headers)["changes"]) == 2


def test_blocks_are_avoided(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    set_hours(client, headers, start=540, end=600)
    new_task(client, headers, deadline_at=DUE, estimated_minutes=50)
    client.post(
        f"{API}/availability/one-off-blocks",
        json={
            "title": "Dentist",
            "start_at": "2026-02-02T09:00:00Z",
            "end_at": "2026-02-02T10:00:00Z",
        },
        headers=headers,
    )
    start = preview(client, headers)["changes"][0]["after_start_at"]
    assert not start.startswith("2026-02-02")


# --- Reporting problems ---------------------------------------------------------------------


def test_not_enough_time_is_reported_with_the_task_name(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    task = new_task(client, headers, title="Big essay", deadline_at=DUE, estimated_minutes=300)

    at_risk = preview(client, headers)["at_risk"]

    assert at_risk[0]["task_id"] == task["id"]
    assert at_risk[0]["task_title"] == "Big essay"
    assert at_risk[0]["shortfall_minutes"] == 300
    assert at_risk[0]["reason"] == "insufficient_time"
    assert at_risk[0]["message"].endswith(".")


def test_overdue_task_is_reported(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    set_hours(client, headers)
    new_task(client, headers, deadline_at="2026-01-01T00:00:00Z")
    proposal = preview(client, headers)
    assert proposal["changes"] == []
    assert proposal["at_risk"][0]["reason"] == "overdue"


def test_work_that_did_not_fit_without_a_deadline_is_not_a_risk(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    set_hours(client, headers, start=540, end=600)
    new_task(client, headers, task_type="reading", deadline_at=None, estimated_minutes=20_000)
    proposal = preview(client, headers)
    assert proposal["at_risk"] == []
    assert proposal["unplaced"][0]["minutes"] > 0


# --- Applying -------------------------------------------------------------------------------


def test_apply_creates_exactly_what_was_previewed(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    set_hours(client, headers)
    new_task(client, headers, deadline_at=DUE, estimated_minutes=100)
    proposal = preview(client, headers)

    response = apply(client, headers, proposal)

    assert response.json() == {"created": 2, "removed": 0}
    listed = sessions(client, headers)
    assert [s["start_at"] for s in listed] == [c["after_start_at"] for c in proposal["changes"]]
    assert all(s["origin"] == "auto" and s["status"] == "planned" for s in listed)
    assert all(s["explanation"] for s in listed)


def test_applying_twice_is_refused(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    proposal = preview(client, headers)
    assert apply(client, headers, proposal).status_code == 200
    assert apply(client, headers, proposal).json()["error"]["code"] == "proposal_closed"


def test_rejecting_discards_the_preview(client: TestClient, db: Session) -> None:
    headers = new_user(client, "UTC")
    set_hours(client, headers)
    new_task(client, headers, deadline_at=DUE)
    proposal = preview(client, headers)

    response = client.post(f"{API}/schedule/proposals/{proposal['id']}/reject", headers=headers)

    assert response.status_code == 204
    assert stored_sessions(db) == []
    assert client.get(f"{API}/schedule/proposals/current", headers=headers).json() is None


@pytest.mark.parametrize("change", ["task", "availability", "preferences", "timezone", "new_task"])
def test_preview_goes_stale_when_inputs_change(
    client: TestClient, db: Session, change: str
) -> None:
    headers = new_user(client, "UTC")
    set_hours(client, headers)
    task = new_task(client, headers, deadline_at=DUE)
    proposal = preview(client, headers)

    if change == "task":
        client.patch(f"{API}/tasks/{task['id']}", json={"priority": 4}, headers=headers)
    elif change == "availability":
        set_hours(client, headers, start=600)
    elif change == "preferences":
        current = client.get(f"{API}/preferences", headers=headers).json()
        client.put(f"{API}/preferences", json=current | {"break_minutes": 20}, headers=headers)
    elif change == "timezone":
        client.patch(f"{API}/users/me", json={"timezone": "Asia/Tokyo"}, headers=headers)
    else:
        new_task(client, headers, title="Another", deadline_at=DUE)

    response = apply(client, headers, proposal)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "proposal_stale"
    assert stored_sessions(db) == []
    assert client.get(f"{API}/schedule/proposals/current", headers=headers).json() is None


# --- Regenerating ---------------------------------------------------------------------------


def test_regenerating_an_unchanged_plan_changes_nothing(client: TestClient) -> None:
    headers, _ = scheduled_user(client, estimated_minutes=100)
    proposal = preview(client, headers)
    assert proposal["trigger"] == "regenerate"
    assert proposal["changes"] == []
    assert proposal["unchanged_sessions"] == 2


def test_finishing_a_task_removes_its_sessions(client: TestClient) -> None:
    headers, task = scheduled_user(client, estimated_minutes=100)
    client.patch(f"{API}/tasks/{task['id']}", json={"status": "completed"}, headers=headers)

    proposal = preview(client, headers)

    assert [c["action"] for c in proposal["changes"]] == ["remove", "remove"]
    assert apply(client, headers, proposal).json() == {"created": 0, "removed": 2}
    assert sessions(client, headers) == []


def test_removed_sessions_are_kept_as_cancelled_history(client: TestClient, db: Session) -> None:
    headers, task = scheduled_user(client, estimated_minutes=50)
    client.patch(f"{API}/tasks/{task['id']}", json={"status": "completed"}, headers=headers)
    apply(client, headers, preview(client, headers))
    assert [s.status for s in stored_sessions(db)] == [SessionStatus.CANCELLED]


def test_a_new_plan_can_reuse_the_time_of_removed_sessions(client: TestClient, db: Session) -> None:
    """Needs the deferred constraint, since new sessions overlap ones being removed."""
    headers, first = scheduled_user(client, estimated_minutes=100)
    new_task(client, headers, title="Urgent", deadline_at="2026-02-02T17:00:00Z", priority=4)
    client.patch(f"{API}/tasks/{first['id']}", json={"priority": 1}, headers=headers)

    response = apply(client, headers, preview(client, headers))

    assert response.status_code == 200
    active = [s for s in stored_sessions(db) if s.status == SessionStatus.PLANNED]
    ordered = sorted(active, key=lambda s: s.start_at)
    assert all(a.end_at <= b.start_at for a, b in zip(ordered, ordered[1:], strict=False))


# Thursday afternoon: a time the planner would not choose on its own for these small tasks.
HAND_PLACED = datetime(2026, 2, 5, 15, 0, tzinfo=UTC)


def _hand_place_first_session(db: Session) -> StudySession:
    """Put a session where only a person would, so that "unchanged" cannot be a coincidence."""
    session = stored_sessions(db)[0]
    session.start_at = HAND_PLACED
    session.end_at = HAND_PLACED + timedelta(minutes=50)
    return session


def _lock_first_session(db: Session) -> StudySession:
    session = _hand_place_first_session(db)
    session.is_locked = True
    db.commit()
    return session


def test_locked_sessions_survive_regeneration(client: TestClient, db: Session) -> None:
    headers, task = scheduled_user(client, estimated_minutes=100)
    locked = _lock_first_session(db)
    client.patch(f"{API}/tasks/{task['id']}", json={"estimated_minutes": 200}, headers=headers)
    client.patch(f"{API}/tasks/{task['id']}", json={"remaining_minutes": 200}, headers=headers)

    proposal = preview(client, headers)

    assert all(c["session_id"] != str(locked.id) for c in proposal["changes"])
    apply(client, headers, proposal)
    assert str(locked.id) in {s["id"] for s in sessions(client, headers)}


def test_locked_minutes_count_toward_the_task(client: TestClient, db: Session) -> None:
    headers, task = scheduled_user(client, estimated_minutes=100)
    _lock_first_session(db)
    client.patch(f"{API}/tasks/{task['id']}", json={"priority": 4}, headers=headers)
    apply(client, headers, preview(client, headers))
    total = sum(
        (datetime.fromisoformat(s["end_at"]) - datetime.fromisoformat(s["start_at"])).seconds // 60
        for s in sessions(client, headers)
    )
    assert total == 100


def test_user_edited_sessions_are_kept(client: TestClient, db: Session) -> None:
    headers, task = scheduled_user(client, estimated_minutes=100)
    edited = _hand_place_first_session(db)
    edited.user_modified_at = NOW
    db.commit()
    client.patch(f"{API}/tasks/{task['id']}", json={"priority": 4}, headers=headers)
    assert all(c["session_id"] != str(edited.id) for c in preview(client, headers)["changes"])


def test_manually_created_sessions_are_kept(client: TestClient, db: Session) -> None:
    headers, task = scheduled_user(client, estimated_minutes=100)
    manual = _hand_place_first_session(db)
    manual.origin = SessionOrigin.MANUAL
    db.commit()
    client.patch(f"{API}/tasks/{task['id']}", json={"priority": 4}, headers=headers)
    assert all(c["session_id"] != str(manual.id) for c in preview(client, headers)["changes"])


def test_unedited_session_in_an_odd_place_is_replaced(client: TestClient, db: Session) -> None:
    """The control for the tests above: without a lock or edit, the session is not protected."""
    headers, task = scheduled_user(client, estimated_minutes=100)
    plain = _hand_place_first_session(db)
    db.commit()
    client.patch(f"{API}/tasks/{task['id']}", json={"priority": 4}, headers=headers)
    assert str(plain.id) in {c["session_id"] for c in preview(client, headers)["changes"]}


def test_session_already_underway_is_kept(client: TestClient, db: Session) -> None:
    headers, task = scheduled_user(client, estimated_minutes=100)
    running = stored_sessions(db)[0]
    client.app.dependency_overrides[utc_now] = lambda: running.start_at + timedelta(minutes=5)  # type: ignore[attr-defined]
    client.patch(f"{API}/tasks/{task['id']}", json={"priority": 4}, headers=headers)
    assert all(c["session_id"] != str(running.id) for c in preview(client, headers)["changes"])


def test_database_rejects_an_apply_that_would_double_book(client: TestClient, db: Session) -> None:
    headers = new_user(client, "UTC")
    set_hours(client, headers)
    task = new_task(client, headers, deadline_at=DUE, estimated_minutes=50)
    proposal = preview(client, headers)
    start = datetime.fromisoformat(proposal["changes"][0]["after_start_at"])
    # Bypasses the API, the way a concurrent request that slipped through would.
    db.add(
        StudySession(
            user_id=uuid.UUID(client.get(f"{API}/users/me", headers=headers).json()["id"]),
            task_id=uuid.UUID(task["id"]),
            start_at=start,
            end_at=start + timedelta(minutes=30),
            origin=SessionOrigin.MANUAL,
        )
    )
    db.commit()

    response = apply(client, headers, proposal)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


# --- Listing --------------------------------------------------------------------------------


def test_sessions_can_be_listed_by_range(client: TestClient) -> None:
    headers, _ = scheduled_user(client, estimated_minutes=300)
    everything = sessions(client, headers)
    first_day = everything[0]["start_at"][:10]
    response = client.get(
        f"{API}/sessions",
        params={"start": f"{first_day}T00:00:00Z", "end": f"{first_day}T23:59:59Z"},
        headers=headers,
    ).json()
    assert 0 < len(response) < len(everything)
    assert all(s["start_at"].startswith(first_day) for s in response)


def test_sessions_are_private(client: TestClient) -> None:
    scheduled_user(client, estimated_minutes=100)
    assert sessions(client, new_user(client, "UTC")) == []

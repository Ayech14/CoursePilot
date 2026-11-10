"""Adaptive planning and manual control through the API."""

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import ProposalChange, StudySession
from app.models.enums import SessionOrigin, SessionStatus
from app.services.scheduling import utc_now
from tests.integration.helpers import API, Headers, field_errors, new_task, new_user

NOW = datetime(2026, 2, 2, 5, 0, tzinfo=UTC)  # Monday.
DUE = "2026-02-20T23:00:00Z"
PREVIEW = f"{API}/schedule/preview"
SESSIONS = f"{API}/sessions"


def set_time(client: TestClient, moment: datetime) -> None:
    client.app.dependency_overrides[utc_now] = lambda: moment  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def frozen_time(client: TestClient) -> Iterator[None]:
    set_time(client, NOW)
    yield


def set_hours(client: TestClient, headers: Headers, start: int = 540, end: int = 1020) -> None:
    windows = [{"day_of_week": d, "start_minute": start, "end_minute": end} for d in range(7)]
    client.put(f"{API}/availability/windows", json={"windows": windows}, headers=headers)


def preview(client: TestClient, headers: Headers, mode: str | None = None) -> dict[str, Any]:
    body = {"mode": mode} if mode else None
    response = client.post(PREVIEW, json=body, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


def apply(
    client: TestClient,
    headers: Headers,
    proposal: dict[str, Any],
    rejected: list[str] | None = None,
) -> Any:
    body = {"rejected_change_ids": rejected} if rejected else None
    return client.post(
        f"{API}/schedule/proposals/{proposal['id']}/apply", json=body, headers=headers
    )


def scheduled(client: TestClient, minutes: int = 300) -> tuple[Headers, dict[str, Any]]:
    headers = new_user(client, "UTC")
    set_hours(client, headers)
    task = new_task(client, headers, deadline_at=DUE, estimated_minutes=minutes)
    assert apply(client, headers, preview(client, headers)).status_code == 200
    return headers, task


def listed(client: TestClient, headers: Headers) -> list[dict[str, Any]]:
    return client.get(SESSIONS, headers=headers).json()


def status(client: TestClient, headers: Headers) -> dict[str, Any]:
    return client.get(f"{API}/schedule/status", headers=headers).json()


def iso(moment: datetime) -> str:
    return moment.isoformat()


def later_of(session: dict[str, Any], **shift: float) -> tuple[str, str]:
    delta = timedelta(**shift)
    start = datetime.fromisoformat(session["start_at"]) + delta
    end = datetime.fromisoformat(session["end_at"]) + delta
    return iso(start), iso(end)


def move(
    client: TestClient, headers: Headers, session_id: str, start: str, end: str, **extra: Any
) -> Any:
    return client.patch(
        f"{SESSIONS}/{session_id}", json={"start_at": start, "end_at": end} | extra, headers=headers
    )


# A Thursday slot inside availability and unused by the small plans below.
FREE_START = datetime(2026, 2, 5, 15, 0, tzinfo=UTC)
FREE_END = FREE_START + timedelta(minutes=50)


# --- Status and missed sessions -------------------------------------------------------------


def test_an_untouched_schedule_needs_no_update(client: TestClient) -> None:
    headers, _ = scheduled(client)
    current = status(client, headers)
    assert current["needs_update"] is False
    assert current["missed_sessions"] == 0


def test_a_session_is_not_missed_during_the_grace_period(client: TestClient, db: Session) -> None:
    headers, _ = scheduled(client)
    first = listed(client, headers)[0]
    set_time(client, datetime.fromisoformat(first["end_at"]) + timedelta(minutes=29))
    status(client, headers)
    assert db.get(StudySession, uuid.UUID(first["id"])).status == SessionStatus.PLANNED


def test_passed_session_is_marked_missed_and_triggers_an_update(
    client: TestClient, db: Session
) -> None:
    headers, _ = scheduled(client)
    first = listed(client, headers)[0]
    set_time(client, datetime.fromisoformat(first["end_at"]) + timedelta(minutes=31))

    current = status(client, headers)

    assert current["missed_sessions"] == 1
    assert current["needs_update"] is True
    assert current["added"] == 1
    assert current["moved"] == 0
    assert db.get(StudySession, uuid.UUID(first["id"])).status == SessionStatus.MISSED


def test_reading_status_changes_no_schedule(client: TestClient) -> None:
    headers, task = scheduled(client)
    client.patch(f"{API}/tasks/{task['id']}", json={"remaining_minutes": 600}, headers=headers)
    before = listed(client, headers)
    status(client, headers)
    assert listed(client, headers) == before


def test_missed_time_is_replanned_without_moving_other_sessions(client: TestClient) -> None:
    headers, _ = scheduled(client)
    sessions = listed(client, headers)
    set_time(client, datetime.fromisoformat(sessions[0]["end_at"]) + timedelta(hours=1))

    proposal = preview(client, headers)

    assert [c["action"] for c in proposal["changes"]] == ["create"]
    assert proposal["stability_percent"] == 100
    assert apply(client, headers, proposal).json()["created"] == 1
    assert {s["id"] for s in sessions[1:]} <= {s["id"] for s in listed(client, headers)}


def test_applying_clears_the_missed_count(client: TestClient) -> None:
    headers, _ = scheduled(client)
    first = listed(client, headers)[0]
    later = datetime.fromisoformat(first["end_at"]) + timedelta(hours=1)
    set_time(client, later)
    apply(client, headers, preview(client, headers))
    set_time(client, later + timedelta(minutes=1))
    assert status(client, headers) | {"at_risk": 0} == {
        "needs_update": False,
        "added": 0,
        "moved": 0,
        "resized": 0,
        "removed": 0,
        "missed_sessions": 0,
        "at_risk": 0,
    }


# --- Events -> minimal repairs --------------------------------------------------------------


def test_task_running_long_adds_without_moving(client: TestClient) -> None:
    headers, task = scheduled(client)
    client.patch(f"{API}/tasks/{task['id']}", json={"remaining_minutes": 400}, headers=headers)
    proposal = preview(client, headers)
    assert {c["action"] for c in proposal["changes"]} == {"create"}
    assert proposal["stability_percent"] == 100


def test_finishing_early_removes_with_a_reason(client: TestClient) -> None:
    headers, task = scheduled(client)
    client.patch(f"{API}/tasks/{task['id']}", json={"status": "completed"}, headers=headers)
    proposal = preview(client, headers)
    assert {c["action"] for c in proposal["changes"]} == {"remove"}
    assert all("no longer needs" in c["explanation"] for c in proposal["changes"])


def test_earlier_deadline_moves_only_late_sessions(client: TestClient) -> None:
    headers, task = scheduled(client, minutes=500)
    sessions = listed(client, headers)
    last = datetime.fromisoformat(sessions[-1]["start_at"])
    client.patch(f"{API}/tasks/{task['id']}", json={"deadline_at": iso(last)}, headers=headers)

    proposal = preview(client, headers)

    assert [c["action"] for c in proposal["changes"]] == ["move"]
    assert proposal["changes"][0]["session_id"] == sessions[-1]["id"]
    assert "after the task's deadline" in proposal["changes"][0]["explanation"]


def test_lost_availability_moves_sessions_with_a_reason(client: TestClient) -> None:
    headers, _ = scheduled(client)
    set_hours(client, headers, start=600, end=1020)
    proposal = preview(client, headers)
    assert proposal["changes"]
    moved = [c for c in proposal["changes"] if c["action"] == "move"]
    assert all("weekly study hours" in c["explanation"] for c in moved)


def test_apply_moves_sessions_and_keeps_their_identity(client: TestClient) -> None:
    headers, _ = scheduled(client)
    set_hours(client, headers, start=600, end=1020)
    proposal = preview(client, headers)
    change = next(c for c in proposal["changes"] if c["action"] == "move")

    result = apply(client, headers, proposal).json()

    assert result["moved"] >= 1
    session = next(s for s in listed(client, headers) if s["id"] == change["session_id"])
    assert session["start_at"] == change["after_start_at"]


def test_regenerate_mode_of_an_unchanged_plan_changes_nothing(client: TestClient) -> None:
    headers, _ = scheduled(client, minutes=100)
    regenerated = preview(client, headers, mode="regenerate")
    assert regenerated["trigger"] == "regenerate"
    assert regenerated["changes"] == []


# --- Accepting and rejecting individual changes ---------------------------------------------


def test_rejected_change_is_skipped(client: TestClient) -> None:
    headers, task = scheduled(client)
    client.patch(f"{API}/tasks/{task['id']}", json={"remaining_minutes": 500}, headers=headers)
    before = len(listed(client, headers))
    proposal = preview(client, headers)
    rejected = proposal["changes"][0]["id"]

    result = apply(client, headers, proposal, [rejected]).json()

    assert result["skipped"] == 1
    assert result["created"] == len(proposal["changes"]) - 1
    assert len(listed(client, headers)) == before + result["created"]


def test_rejecting_a_move_leaves_the_session_in_place(client: TestClient) -> None:
    headers, _ = scheduled(client)
    set_hours(client, headers, start=600, end=1020)
    proposal = preview(client, headers)
    change = next(c for c in proposal["changes"] if c["action"] == "move")
    others_moved = [
        c["id"] for c in proposal["changes"] if c["id"] != change["id"] and c["action"] == "move"
    ]

    response = apply(client, headers, proposal, [change["id"], *others_moved])

    assert response.status_code == 200
    session = next(s for s in listed(client, headers) if s["id"] == change["session_id"])
    assert session["start_at"] == change["before_start_at"]


def test_choices_that_collide_are_refused_and_keep_the_preview_open(
    client: TestClient, db: Session
) -> None:
    headers, task = scheduled(client, minutes=50)
    original = listed(client, headers)[0]
    set_hours(client, headers, start=600, end=1020)
    client.patch(f"{API}/tasks/{task['id']}", json={"remaining_minutes": 100}, headers=headers)
    proposal = preview(client, headers)
    create = next(c for c in proposal["changes"] if c["action"] == "create")
    move_change = next(c for c in proposal["changes"] if c["action"] == "move")
    # Make the two changes collide if only the new session is accepted.
    stored = db.scalars(select(ProposalChange).where(ProposalChange.id == create["id"])).one()
    stored.after_start_at = datetime.fromisoformat(original["start_at"])
    stored.after_end_at = datetime.fromisoformat(original["end_at"])
    db.commit()

    response = apply(client, headers, proposal, [move_change["id"]])

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "proposal_conflict"
    current = client.get(f"{API}/schedule/proposals/current", headers=headers).json()
    assert current["id"] == proposal["id"]


# --- Moving and resizing --------------------------------------------------------------------


def test_moving_to_a_free_time_works_and_marks_it_edited(client: TestClient) -> None:
    headers, _ = scheduled(client, minutes=100)
    first = listed(client, headers)[0]

    response = move(client, headers, first["id"], iso(FREE_START), iso(FREE_END))

    assert response.status_code == 200
    assert response.json()["is_user_modified"] is True
    assert response.json()["origin"] == "auto"
    assert datetime.fromisoformat(response.json()["start_at"]) == FREE_START


def test_resizing_works(client: TestClient) -> None:
    headers, _ = scheduled(client, minutes=100)
    first = listed(client, headers)[0]
    start = datetime.fromisoformat(first["start_at"])
    response = move(client, headers, first["id"], iso(start), iso(start + timedelta(minutes=30)))
    assert response.status_code == 200
    assert response.json()["end_at"] != first["end_at"]


def test_overlap_is_refused_with_alternatives(client: TestClient) -> None:
    headers, _ = scheduled(client, minutes=100)
    first, second = listed(client, headers)[:2]

    response = move(client, headers, first["id"], second["start_at"], second["end_at"])

    assert response.status_code == 409
    error = response.json()["error"]
    assert error["code"] == "session_conflict"
    assert error["details"]["conflicts"][0]["session_id"] == second["id"]
    assert error["details"]["conflicts"][0]["message"].endswith(".")
    assert error["details"]["alternatives"]


def test_overlap_cannot_be_acknowledged_away(client: TestClient) -> None:
    headers, _ = scheduled(client, minutes=100)
    first, second = listed(client, headers)[:2]
    response = move(
        client,
        headers,
        first["id"],
        second["start_at"],
        second["end_at"],
        acknowledge_warnings=True,
    )
    assert response.status_code == 409


def test_refused_move_changes_nothing(client: TestClient) -> None:
    headers, _ = scheduled(client, minutes=100)
    before = listed(client, headers)
    move(client, headers, before[0]["id"], before[1]["start_at"], before[1]["end_at"])
    assert listed(client, headers) == before


def test_warning_needs_confirmation_then_succeeds(client: TestClient) -> None:
    headers, _ = scheduled(client, minutes=100)
    first = listed(client, headers)[0]
    night = datetime(2026, 2, 5, 23, 0, tzinfo=UTC)  # Outside 09:00 to 17:00.
    end = night + timedelta(minutes=50)

    warned = move(client, headers, first["id"], iso(night), iso(end))
    confirmed = move(client, headers, first["id"], iso(night), iso(end), acknowledge_warnings=True)

    assert warned.status_code == 409
    assert warned.json()["error"]["code"] == "placement_warnings"
    assert warned.json()["error"]["details"]["warnings"][0]["kind"] == "outside_availability"
    assert confirmed.status_code == 200


def test_cannot_move_into_the_past(client: TestClient) -> None:
    headers, _ = scheduled(client, minutes=100)
    first = listed(client, headers)[0]
    past = NOW - timedelta(days=1)
    response = move(
        client,
        headers,
        first["id"],
        iso(past),
        iso(past + timedelta(minutes=50)),
        acknowledge_warnings=True,
    )
    assert response.status_code == 409
    assert response.json()["error"]["details"]["conflicts"][0]["kind"] == "in_past"


@pytest.mark.parametrize("minutes", [0, 4, 481])
def test_session_length_is_validated(client: TestClient, minutes: int) -> None:
    headers, _ = scheduled(client, minutes=100)
    first = listed(client, headers)[0]
    response = move(
        client, headers, first["id"], iso(FREE_START), iso(FREE_START + timedelta(minutes=minutes))
    )
    assert list(field_errors(response)) == ["end_at"]


def test_missed_session_cannot_be_moved(client: TestClient) -> None:
    headers, _ = scheduled(client, minutes=100)
    first = listed(client, headers)[0]
    set_time(client, datetime.fromisoformat(first["end_at"]) + timedelta(hours=1))
    status(client, headers)
    response = move(client, headers, first["id"], iso(FREE_START), iso(FREE_END))
    assert response.json()["error"]["code"] == "session_not_editable"


def test_moved_session_is_respected_by_later_plans(client: TestClient) -> None:
    headers, _ = scheduled(client, minutes=100)
    first = listed(client, headers)[0]
    move(client, headers, first["id"], iso(FREE_START), iso(FREE_END))

    for mode in ("repair", "regenerate"):
        proposal = preview(client, headers, mode)
        assert first["id"] not in {c["session_id"] for c in proposal["changes"]}


def test_edit_makes_an_open_preview_stale(client: TestClient) -> None:
    headers, _ = scheduled(client, minutes=100)
    first = listed(client, headers)[0]
    proposal = preview(client, headers)
    move(client, headers, first["id"], iso(FREE_START), iso(FREE_END))
    assert apply(client, headers, proposal).json()["error"]["code"] == "proposal_stale"


# --- Locking --------------------------------------------------------------------------------


def lock(client: TestClient, headers: Headers, session_id: str, action: str = "lock") -> Any:
    return client.post(f"{SESSIONS}/{session_id}/{action}", headers=headers)


def test_lock_and_unlock(client: TestClient) -> None:
    headers, _ = scheduled(client, minutes=100)
    first = listed(client, headers)[0]
    assert lock(client, headers, first["id"]).json()["is_locked"] is True
    assert lock(client, headers, first["id"], "unlock").json()["is_locked"] is False


def test_locked_session_stays_even_if_its_time_becomes_unavailable(client: TestClient) -> None:
    headers, _ = scheduled(client)
    first = listed(client, headers)[0]
    lock(client, headers, first["id"])
    set_hours(client, headers, start=720, end=1020)

    for mode in ("repair", "regenerate"):
        proposal = preview(client, headers, mode)
        assert first["id"] not in {c["session_id"] for c in proposal["changes"]}


def test_locked_session_can_still_be_moved_by_the_student(client: TestClient) -> None:
    headers, _ = scheduled(client, minutes=100)
    first = listed(client, headers)[0]
    lock(client, headers, first["id"])
    response = move(client, headers, first["id"], iso(FREE_START), iso(FREE_END))
    assert response.status_code == 200
    assert response.json()["is_locked"] is True


# --- Creating, deleting, checking -----------------------------------------------------------


def test_create_manual_session(client: TestClient, db: Session) -> None:
    headers, task = scheduled(client, minutes=100)
    response = client.post(
        SESSIONS,
        json={"task_id": task["id"], "start_at": iso(FREE_START), "end_at": iso(FREE_END)},
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["origin"] == "manual"
    assert response.json()["is_user_modified"] is True
    assert db.scalars(select(StudySession).where(StudySession.origin == SessionOrigin.MANUAL)).one()


def test_cannot_add_a_session_to_a_finished_task(client: TestClient) -> None:
    headers, task = scheduled(client, minutes=100)
    client.patch(f"{API}/tasks/{task['id']}", json={"status": "completed"}, headers=headers)
    response = client.post(
        SESSIONS,
        json={"task_id": task["id"], "start_at": iso(FREE_START), "end_at": iso(FREE_END)},
        headers=headers,
    )
    assert list(field_errors(response)) == ["task_id"]


def test_deleted_session_time_returns_to_the_plan(client: TestClient) -> None:
    headers, _ = scheduled(client, minutes=100)
    first = listed(client, headers)[0]

    assert client.delete(f"{SESSIONS}/{first['id']}", headers=headers).status_code == 204

    assert first["id"] not in {s["id"] for s in listed(client, headers)}
    assert status(client, headers)["added"] == 1


def test_check_placement_saves_nothing(client: TestClient) -> None:
    headers, _ = scheduled(client, minutes=100)
    first, second = listed(client, headers)[:2]
    before = listed(client, headers)

    result = client.post(
        f"{SESSIONS}/check-placement",
        json={
            "session_id": first["id"],
            "start_at": second["start_at"],
            "end_at": second["end_at"],
        },
        headers=headers,
    ).json()

    assert result["ok"] is False
    assert result["conflicts"][0]["kind"] == "overlap"
    assert result["alternatives"]
    assert listed(client, headers) == before


def test_check_placement_for_a_clean_time(client: TestClient) -> None:
    headers, task = scheduled(client, minutes=100)
    result = client.post(
        f"{SESSIONS}/check-placement",
        json={"task_id": task["id"], "start_at": iso(FREE_START), "end_at": iso(FREE_END)},
        headers=headers,
    ).json()
    assert result == {"ok": True, "conflicts": [], "warnings": [], "alternatives": []}


def test_check_placement_needs_a_task_or_session(client: TestClient) -> None:
    response = client.post(
        f"{SESSIONS}/check-placement",
        json={"start_at": iso(FREE_START), "end_at": iso(FREE_END)},
        headers=new_user(client, "UTC"),
    )
    assert list(field_errors(response)) == ["task_id"]


def test_cannot_check_or_create_against_another_users_task(client: TestClient) -> None:
    _, task = scheduled(client, minutes=100)
    intruder = new_user(client, "UTC")
    body = {"task_id": task["id"], "start_at": iso(FREE_START), "end_at": iso(FREE_END)}
    assert (
        client.post(f"{SESSIONS}/check-placement", json=body, headers=intruder).status_code == 404
    )
    assert list(field_errors(client.post(SESSIONS, json=body, headers=intruder))) == ["task_id"]

"""The study timer through the API, with the clock under the test's control."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.services.scheduling import utc_now
from tests.integration.helpers import API, Headers, field_errors, new_task, new_user

NOW = datetime(2026, 2, 2, 12, 0, tzinfo=UTC)  # Monday.
DUE = "2026-02-20T23:00:00Z"
SESSIONS = f"{API}/sessions"


def set_time(client: TestClient, moment: datetime) -> None:
    client.app.dependency_overrides[utc_now] = lambda: moment  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def frozen_time(client: TestClient) -> Iterator[None]:
    set_time(client, NOW)
    yield


def session_at(
    client: TestClient, headers: Headers, task_id: str, start: datetime, minutes: int = 50
) -> str:
    response = client.post(
        SESSIONS,
        json={
            "task_id": task_id,
            "start_at": start.isoformat(),
            "end_at": (start + timedelta(minutes=minutes)).isoformat(),
            "acknowledge_warnings": True,
        },
        headers=headers,
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


def act(client: TestClient, headers: Headers, session: str, verb: str, **body: Any) -> Any:
    return client.post(f"{SESSIONS}/{session}/{verb}", json=body or None, headers=headers)


def ready(client: TestClient, minutes: int = 300) -> tuple[Headers, str, str]:
    headers = new_user(client, "UTC")
    task = new_task(client, headers, deadline_at=DUE, estimated_minutes=minutes)["id"]
    return headers, task, session_at(client, headers, task, NOW + timedelta(minutes=10))


def task_of(client: TestClient, headers: Headers, task: str) -> dict[str, Any]:
    return client.get(f"{API}/tasks/{task}", headers=headers).json()


def active(client: TestClient, headers: Headers) -> Any:
    return client.get(f"{SESSIONS}/active", headers=headers).json()


def code(response: Any) -> str:
    assert response.status_code == 409, response.text
    return response.json()["error"]["code"]


def test_no_active_timer_at_first(client: TestClient) -> None:
    headers, _, _ = ready(client)
    assert active(client, headers) is None


def test_start_opens_the_timer_and_marks_the_task_started(client: TestClient) -> None:
    headers, task, session = ready(client)
    body = act(client, headers, session, "start").json()
    assert body["running"] is True
    assert body["elapsed_seconds"] == 0
    assert body["session"]["status"] == "in_progress"
    assert task_of(client, headers, task)["status"] == "in_progress"


def test_starting_early_on_the_same_day_is_allowed(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    task = new_task(client, headers, deadline_at=DUE)["id"]
    session = session_at(client, headers, task, NOW + timedelta(hours=8))
    assert act(client, headers, session, "start").status_code == 200


def test_a_later_local_day_cannot_be_started(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    task = new_task(client, headers, deadline_at=DUE)["id"]
    session = session_at(client, headers, task, NOW + timedelta(days=1))
    assert code(act(client, headers, session, "start")) == "session_not_today"


@pytest.mark.parametrize(
    ("timezone", "allowed"),
    [("Asia/Tokyo", False), ("America/Los_Angeles", True)],
)
def test_today_means_the_students_local_today(
    client: TestClient, timezone: str, allowed: bool
) -> None:
    # 2026-02-03 01:00 UTC is already the 3rd's morning in Tokyo, the 2nd's evening in L.A.
    # At 12:00 UTC on the 2nd it is 21:00 in Tokyo, so the session is on Tokyo's tomorrow.
    headers = new_user(client, timezone)
    task = new_task(client, headers, deadline_at=DUE)["id"]
    session = session_at(client, headers, task, datetime(2026, 2, 3, 1, 0, tzinfo=UTC))
    response = act(client, headers, session, "start")
    assert response.status_code == (200 if allowed else 409)


def test_elapsed_time_excludes_paused_time(client: TestClient) -> None:
    headers, task, session = ready(client)
    act(client, headers, session, "start")

    set_time(client, NOW + timedelta(minutes=10))
    assert active(client, headers)["elapsed_seconds"] == 600
    paused = act(client, headers, session, "pause").json()
    assert (paused["running"], paused["elapsed_seconds"]) == (False, 600)

    set_time(client, NOW + timedelta(minutes=40))
    assert active(client, headers)["elapsed_seconds"] == 600
    assert act(client, headers, session, "resume").json()["running"] is True

    set_time(client, NOW + timedelta(minutes=45))
    finished = act(client, headers, session, "finish").json()
    assert finished["status"] == "completed"
    assert finished["actual_minutes"] == 15
    updated = task_of(client, headers, task)
    assert (updated["actual_minutes"], updated["remaining_minutes"]) == (15, 285)
    assert active(client, headers) is None


def test_only_one_session_can_be_open(client: TestClient) -> None:
    headers, task, first = ready(client)
    second = session_at(client, headers, task, NOW + timedelta(hours=2))
    act(client, headers, first, "start")
    assert code(act(client, headers, second, "start")) == "timer_active"
    act(client, headers, first, "pause")
    assert code(act(client, headers, second, "start")) == "timer_active"


@pytest.mark.parametrize("verb", ["pause", "resume", "finish", "discard"])
def test_a_planned_session_has_no_timer_to_act_on(client: TestClient, verb: str) -> None:
    headers, _, session = ready(client)
    assert code(act(client, headers, session, verb)) == "timer_state"


def test_states_must_be_followed(client: TestClient) -> None:
    headers, _, session = ready(client)
    act(client, headers, session, "start")
    assert code(act(client, headers, session, "start")) == "timer_state"
    assert code(act(client, headers, session, "resume")) == "timer_state"
    act(client, headers, session, "pause")
    assert code(act(client, headers, session, "pause")) == "timer_state"
    assert act(client, headers, session, "finish").status_code == 200
    assert code(act(client, headers, session, "finish")) == "timer_state"


def test_a_completed_tasks_session_cannot_start(client: TestClient) -> None:
    headers, task, session = ready(client)
    client.post(f"{API}/tasks/{task}/progress", json={"mark_completed": True}, headers=headers)
    assert code(act(client, headers, session, "start")) == "task_completed"


def test_a_session_past_its_grace_period_is_missed_not_startable(client: TestClient) -> None:
    headers, _, session = ready(client)
    set_time(client, NOW + timedelta(hours=3))
    assert code(act(client, headers, session, "start")) == "timer_state"


def test_finishing_can_complete_the_task(client: TestClient) -> None:
    headers, task, session = ready(client)
    act(client, headers, session, "start")
    set_time(client, NOW + timedelta(minutes=30))
    act(client, headers, session, "finish", mark_task_completed=True)
    updated = task_of(client, headers, task)
    assert updated["status"] == "completed"
    assert updated["remaining_minutes"] == 0
    assert updated["completed_at"].startswith("2026-02-02T12:30")


def test_finishing_can_set_the_remaining_work(client: TestClient) -> None:
    headers, task, session = ready(client)
    act(client, headers, session, "start")
    set_time(client, NOW + timedelta(minutes=30))
    act(client, headers, session, "finish", remaining_minutes=60)
    updated = task_of(client, headers, task)
    assert (updated["remaining_minutes"], updated["actual_minutes"]) == (60, 30)


def test_zero_remaining_completes_the_task(client: TestClient) -> None:
    headers, task, session = ready(client)
    act(client, headers, session, "start")
    act(client, headers, session, "finish", remaining_minutes=0)
    assert task_of(client, headers, task)["status"] == "completed"


def test_going_over_the_estimate_does_not_complete_the_task(client: TestClient) -> None:
    headers, task, session = ready(client, minutes=30)
    act(client, headers, session, "start")
    set_time(client, NOW + timedelta(minutes=50))
    act(client, headers, session, "finish")
    updated = task_of(client, headers, task)
    assert updated["status"] == "in_progress"
    assert updated["remaining_minutes"] == 15


def test_a_forgotten_timer_can_be_corrected_down(client: TestClient) -> None:
    headers, task, session = ready(client)
    act(client, headers, session, "start")
    set_time(client, NOW + timedelta(minutes=20))
    act(client, headers, session, "pause")
    set_time(client, NOW + timedelta(minutes=30))
    act(client, headers, session, "resume")
    set_time(client, NOW + timedelta(hours=5))

    finished = act(client, headers, session, "finish", actual_minutes=25).json()
    assert finished["actual_minutes"] == 25
    assert task_of(client, headers, task)["actual_minutes"] == 25

    week = client.get(f"{API}/dashboard", headers=headers).json()["week"]
    assert week["studied_minutes"] == 25


def test_correcting_to_zero_records_no_time(client: TestClient) -> None:
    headers, task, session = ready(client)
    act(client, headers, session, "start")
    set_time(client, NOW + timedelta(minutes=20))
    assert act(client, headers, session, "finish", actual_minutes=0).json()["actual_minutes"] == 0
    assert task_of(client, headers, task)["actual_minutes"] == 0


def test_time_cannot_be_invented_at_finish(client: TestClient) -> None:
    headers, task, session = ready(client)
    act(client, headers, session, "start")
    set_time(client, NOW + timedelta(minutes=20))
    response = act(client, headers, session, "finish", actual_minutes=21)
    assert "20 minutes" in field_errors(response)["actual_minutes"]
    assert task_of(client, headers, task)["actual_minutes"] == 0
    assert active(client, headers)["running"] is True


def test_task_finished_elsewhere_still_gets_the_time(client: TestClient) -> None:
    headers, task, session = ready(client)
    act(client, headers, session, "start")
    client.patch(f"{API}/tasks/{task}", json={"status": "completed"}, headers=headers)
    set_time(client, NOW + timedelta(minutes=30))
    assert act(client, headers, session, "finish").status_code == 200
    updated = task_of(client, headers, task)
    assert (updated["status"], updated["actual_minutes"]) == ("completed", 30)


def test_discard_restores_the_session_and_records_nothing(client: TestClient) -> None:
    headers, task, session = ready(client)
    act(client, headers, session, "start")
    set_time(client, NOW + timedelta(minutes=5))
    assert act(client, headers, session, "discard").status_code == 204
    assert active(client, headers) is None
    assert task_of(client, headers, task)["actual_minutes"] == 0
    listed = client.get(SESSIONS, headers=headers).json()
    assert (listed[0]["status"], listed[0]["actual_minutes"]) == ("planned", 0)
    assert client.get(f"{API}/dashboard", headers=headers).json()["week"]["studied_minutes"] == 0


def test_a_started_session_cannot_be_moved(client: TestClient) -> None:
    headers, _, session = ready(client)
    act(client, headers, session, "start")
    response = client.patch(
        f"{SESSIONS}/{session}",
        json={
            "start_at": (NOW + timedelta(hours=4)).isoformat(),
            "end_at": (NOW + timedelta(hours=5)).isoformat(),
            "acknowledge_warnings": True,
        },
        headers=headers,
    )
    assert code(response) == "session_not_editable"


def test_a_running_session_is_never_marked_missed(client: TestClient) -> None:
    headers, _, session = ready(client)
    act(client, headers, session, "start")
    set_time(client, NOW + timedelta(hours=6))
    client.get(SESSIONS, headers=headers)
    assert active(client, headers)["session"]["status"] == "in_progress"


def test_starting_makes_an_open_preview_stale(client: TestClient) -> None:
    headers, _, session = ready(client)
    proposal = client.post(f"{API}/schedule/preview", headers=headers).json()
    act(client, headers, session, "start")
    response = client.post(f"{API}/schedule/proposals/{proposal['id']}/apply", headers=headers)
    assert code(response) == "proposal_stale"


def test_finished_work_counts_toward_todays_limit(client: TestClient) -> None:
    def planned_today(headers: Headers) -> int:
        proposal = client.post(f"{API}/schedule/preview", headers=headers).json()
        return sum(1 for c in proposal["changes"] if c["after_start_at"].startswith("2026-02-02"))

    headers, task, session = ready(client, minutes=4000)
    windows = [{"day_of_week": d, "start_minute": 780, "end_minute": 1320} for d in range(7)]
    client.put(f"{API}/availability/windows", json={"windows": windows}, headers=headers)
    prefs = client.get(f"{API}/preferences", headers=headers).json()
    client.put(f"{API}/preferences", json=prefs | {"max_daily_minutes": 120}, headers=headers)
    client.delete(f"{SESSIONS}/{session}", headers=headers)
    assert planned_today(headers) == 2

    second = session_at(client, headers, task, NOW + timedelta(minutes=5))
    act(client, headers, second, "start")
    set_time(client, NOW + timedelta(minutes=50))
    act(client, headers, second, "finish")
    assert planned_today(headers) == 1


def test_listing_shows_actual_minutes_for_finished_sessions(client: TestClient) -> None:
    headers, _, session = ready(client)
    act(client, headers, session, "start")
    set_time(client, NOW + timedelta(minutes=40))
    act(client, headers, session, "finish")
    listed = client.get(SESSIONS, params={"start": NOW.isoformat()}, headers=headers).json()
    assert listed[0]["actual_minutes"] == 40


# --- Starting a timer on any task, without a planned session ---

QUICK = f"{SESSIONS}/quick-start"


def quick(client: TestClient, headers: Headers, task: str) -> Any:
    return client.post(QUICK, json={"task_id": task}, headers=headers)


def fresh(client: TestClient) -> tuple[Headers, str]:
    headers = new_user(client, "UTC")
    return headers, new_task(client, headers, deadline_at=DUE, estimated_minutes=300)["id"]


def test_quick_start_times_a_task_right_away(client: TestClient) -> None:
    headers, task = fresh(client)
    response = quick(client, headers, task)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["running"] is True
    session = body["session"]
    assert (session["status"], session["origin"], session["unplanned"]) == (
        "in_progress",
        "manual",
        True,
    )
    # The slot is one preferred session long (50 minutes by default).
    assert session["start_at"] == "2026-02-02T12:00:00Z"
    assert session["end_at"] == "2026-02-02T12:50:00Z"
    assert task_of(client, headers, task)["status"] == "in_progress"


def test_quick_start_stops_its_slot_before_the_next_planned_session(client: TestClient) -> None:
    headers, task = fresh(client)
    other = new_task(client, headers, deadline_at=DUE)["id"]
    session_at(client, headers, other, NOW + timedelta(minutes=20))
    body = quick(client, headers, task).json()
    assert body["session"]["end_at"] == "2026-02-02T12:20:00Z"


def test_quick_start_refuses_when_another_task_is_planned_now(client: TestClient) -> None:
    headers, task = fresh(client)
    other = new_task(client, headers, title="Lab report", deadline_at=DUE)["id"]
    session_at(client, headers, other, NOW + timedelta(minutes=10))
    set_time(client, NOW + timedelta(minutes=20))  # Sessions can only be planned ahead.
    response = quick(client, headers, task)
    assert code(response) == "session_conflict"
    assert "Lab report" in response.json()["error"]["message"]


def test_quick_start_uses_the_planned_session_for_the_same_task(client: TestClient) -> None:
    headers, task = fresh(client)
    planned = session_at(client, headers, task, NOW + timedelta(minutes=10))
    set_time(client, NOW + timedelta(minutes=20))
    body = quick(client, headers, task).json()
    assert body["session"]["id"] == planned
    assert len(client.get(SESSIONS, headers=headers).json()) == 1


def test_quick_start_refuses_a_slot_under_a_minute(client: TestClient) -> None:
    headers, task = fresh(client)
    other = new_task(client, headers, deadline_at=DUE)["id"]
    session_at(client, headers, other, NOW + timedelta(seconds=30))
    assert code(quick(client, headers, task)) == "session_conflict"


def test_quick_start_needs_no_open_timer_and_an_open_task(client: TestClient) -> None:
    headers, task = fresh(client)
    quick(client, headers, task)
    other = new_task(client, headers, deadline_at=DUE)["id"]
    assert code(quick(client, headers, other)) == "timer_active"

    done = new_task(client, headers, deadline_at=DUE)["id"]
    client.post(f"{API}/tasks/{done}/progress", json={"mark_completed": True}, headers=headers)
    active_id = active(client, headers)["session"]["id"]
    act(client, headers, active_id, "discard")
    assert code(quick(client, headers, done)) == "task_completed"


def test_quick_start_on_someone_elses_task_is_not_found(client: TestClient) -> None:
    _, task = fresh(client)
    stranger = new_user(client, "UTC")
    assert quick(client, stranger, task).status_code == 404


def test_finishing_a_quick_session_shrinks_it_to_the_time_worked(client: TestClient) -> None:
    headers, task = fresh(client)
    session = quick(client, headers, task).json()["session"]["id"]
    set_time(client, NOW + timedelta(minutes=25))
    finished = act(client, headers, session, "finish")
    assert finished.status_code == 200, finished.text
    body = finished.json()
    assert (body["status"], body["actual_minutes"]) == ("completed", 25)
    assert body["end_at"] == "2026-02-02T12:25:00Z"
    assert task_of(client, headers, task)["actual_minutes"] == 25


def test_a_quick_session_can_run_past_its_slot(client: TestClient) -> None:
    headers, task = fresh(client)
    session = quick(client, headers, task).json()["session"]["id"]
    set_time(client, NOW + timedelta(minutes=80))
    body = act(client, headers, session, "finish").json()
    assert body["actual_minutes"] == 80
    assert body["end_at"] == "2026-02-02T13:20:00Z"


def test_discarding_a_quick_session_removes_it(client: TestClient) -> None:
    headers, task = fresh(client)
    session = quick(client, headers, task).json()["session"]["id"]
    set_time(client, NOW + timedelta(minutes=5))
    assert act(client, headers, session, "discard").status_code == 204
    assert client.get(SESSIONS, headers=headers).json() == []
    assert active(client, headers) is None
    assert task_of(client, headers, task)["actual_minutes"] == 0


def test_quick_start_validates_the_body(client: TestClient) -> None:
    headers, _ = fresh(client)
    response = client.post(QUICK, json={"task_id": "nope"}, headers=headers)
    assert "task_id" in field_errors(response)

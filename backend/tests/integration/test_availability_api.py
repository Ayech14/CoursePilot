from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.integration.helpers import API, field_errors, new_user

WINDOWS = f"{API}/availability/windows"
RECURRING = f"{API}/availability/recurring-blocks"
ONE_OFF = f"{API}/availability/one-off-blocks"
PREFERENCES = f"{API}/preferences"

VALID_PREFERENCES = {
    "preferred_session_minutes": 45,
    "min_session_minutes": 20,
    "break_minutes": 15,
    "max_daily_minutes": 300,
    "deadline_buffer_hours": 24,
    "planning_horizon_days": 42,
}


def window(day: int = 0, start: int = 540, end: int = 720) -> dict[str, int]:
    return {"day_of_week": day, "start_minute": start, "end_minute": end}


def put_windows(client: TestClient, headers: dict[str, str], *windows: dict[str, int]) -> Any:
    return client.put(WINDOWS, json={"windows": list(windows)}, headers=headers)


def test_windows_start_empty(client: TestClient) -> None:
    assert client.get(WINDOWS, headers=new_user(client)).json() == []


def test_windows_are_saved_in_week_order(client: TestClient) -> None:
    headers = new_user(client)
    response = put_windows(client, headers, window(2), window(0, 780, 900), window(0, 540, 720))

    assert response.status_code == 200
    saved = [(w["day_of_week"], w["start_minute"]) for w in response.json()]
    assert saved == [(0, 540), (0, 780), (2, 540)]


def test_saving_windows_replaces_the_previous_week(client: TestClient) -> None:
    headers = new_user(client)
    put_windows(client, headers, window(0), window(1))
    put_windows(client, headers, window(4))
    assert [w["day_of_week"] for w in client.get(WINDOWS, headers=headers).json()] == [4]


def test_windows_can_be_cleared(client: TestClient) -> None:
    headers = new_user(client)
    put_windows(client, headers, window())
    assert put_windows(client, headers).json() == []


def test_window_may_run_to_end_of_day(client: TestClient) -> None:
    response = put_windows(client, new_user(client), window(6, 1200, 1440))
    assert response.json()[0]["end_minute"] == 1440


def test_adjacent_windows_allowed(client: TestClient) -> None:
    response = put_windows(client, new_user(client), window(0, 540, 600), window(0, 600, 660))
    assert response.status_code == 200


def test_overlap_reports_the_offending_row(client: TestClient) -> None:
    headers = new_user(client)
    response = put_windows(client, headers, window(0, 540, 720), window(0, 700, 800))
    assert list(field_errors(response)) == ["windows.1"]


def test_rejected_save_keeps_existing_windows(client: TestClient) -> None:
    headers = new_user(client)
    put_windows(client, headers, window(3))
    put_windows(client, headers, window(0, 540, 720), window(0, 700, 800))
    assert [w["day_of_week"] for w in client.get(WINDOWS, headers=headers).json()] == [3]


@pytest.mark.parametrize(
    ("bad", "field"),
    [
        (window(7), "windows.0.day_of_week"),
        (window(-1), "windows.0.day_of_week"),
        (window(0, 720, 720), "windows.0.end_minute"),
        (window(0, 720, 600), "windows.0.end_minute"),
        (window(0, -5, 600), "windows.0.start_minute"),
        (window(0, 600, 1441), "windows.0.end_minute"),
    ],
)
def test_invalid_window_rejected(client: TestClient, bad: dict[str, int], field: str) -> None:
    assert list(field_errors(put_windows(client, new_user(client), bad))) == [field]


# --- Recurring blocks -----------------------------------------------------------------------


def recurring(title: str = "Lecture", day: int = 1) -> dict[str, Any]:
    return {"title": title, "day_of_week": day, "start_minute": 600, "end_minute": 690}


def test_recurring_block_lifecycle(client: TestClient) -> None:
    headers = new_user(client)
    block = client.post(RECURRING, json=recurring(), headers=headers).json()

    updated = client.put(
        f"{RECURRING}/{block['id']}", json=recurring("Lab", 3), headers=headers
    ).json()

    assert (updated["title"], updated["day_of_week"]) == ("Lab", 3)
    assert len(client.get(RECURRING, headers=headers).json()) == 1
    assert client.delete(f"{RECURRING}/{block['id']}", headers=headers).status_code == 204
    assert client.get(RECURRING, headers=headers).json() == []


def test_recurring_blocks_are_sorted_by_week_time(client: TestClient) -> None:
    headers = new_user(client)
    client.post(RECURRING, json=recurring("Thursday", 3), headers=headers)
    client.post(RECURRING, json=recurring("Monday", 0), headers=headers)
    titles = [b["title"] for b in client.get(RECURRING, headers=headers).json()]
    assert titles == ["Monday", "Thursday"]


def test_recurring_block_requires_a_title_and_valid_times(client: TestClient) -> None:
    headers = new_user(client)
    no_title = client.post(RECURRING, json=recurring("  "), headers=headers)
    backwards = client.post(
        RECURRING, json=recurring() | {"start_minute": 700, "end_minute": 600}, headers=headers
    )
    assert list(field_errors(no_title)) == ["title"]
    assert list(field_errors(backwards)) == ["end_minute"]


# --- One-off blocks -------------------------------------------------------------------------


def one_off(
    start: str = "2026-12-24T09:00:00Z", end: str = "2026-12-26T09:00:00Z"
) -> dict[str, str]:
    return {"title": "Trip", "start_at": start, "end_at": end}


def test_one_off_block_lifecycle(client: TestClient) -> None:
    headers = new_user(client)
    block = client.post(ONE_OFF, json=one_off(), headers=headers).json()

    response = client.put(
        f"{ONE_OFF}/{block['id']}",
        json=one_off("2026-12-25T09:00:00Z") | {"title": "Short trip"},
        headers=headers,
    )

    assert response.json()["title"] == "Short trip"
    assert client.delete(f"{ONE_OFF}/{block['id']}", headers=headers).status_code == 204


def test_one_off_range_filter_returns_overlapping_blocks(client: TestClient) -> None:
    headers = new_user(client)
    client.post(ONE_OFF, json=one_off("2026-12-01T00:00Z", "2026-12-02T00:00Z"), headers=headers)
    client.post(ONE_OFF, json=one_off("2026-12-10T00:00Z", "2026-12-12T00:00Z"), headers=headers)

    found = client.get(
        ONE_OFF,
        params={"ends_after": "2026-12-11T00:00Z", "starts_before": "2026-12-20T00:00Z"},
        headers=headers,
    ).json()

    assert len(found) == 1
    assert found[0]["start_at"].startswith("2026-12-10")


@pytest.mark.parametrize(
    "body",
    [
        one_off("2026-12-26T09:00:00Z", "2026-12-24T09:00:00Z"),
        one_off("2026-12-24T09:00:00Z", "2026-12-24T09:00:00Z"),
    ],
)
def test_one_off_block_must_end_after_start(client: TestClient, body: dict[str, str]) -> None:
    response = client.post(ONE_OFF, json=body, headers=new_user(client))
    assert list(field_errors(response)) == ["end_at"]


def test_one_off_block_rejects_times_without_a_zone(client: TestClient) -> None:
    response = client.post(
        ONE_OFF,
        json=one_off("2026-12-24T09:00:00", "2026-12-26T09:00:00Z"),
        headers=new_user(client),
    )
    assert list(field_errors(response)) == ["start_at"]


# --- Preferences ----------------------------------------------------------------------------


def test_new_users_have_default_preferences(client: TestClient) -> None:
    preferences = client.get(PREFERENCES, headers=new_user(client)).json()
    assert preferences["preferred_session_minutes"] == 50
    assert preferences["max_daily_minutes"] == 360


def test_preferences_can_be_updated(client: TestClient) -> None:
    headers = new_user(client)
    assert (
        client.put(PREFERENCES, json=VALID_PREFERENCES, headers=headers).json() == VALID_PREFERENCES
    )
    assert client.get(PREFERENCES, headers=headers).json() == VALID_PREFERENCES


@pytest.mark.parametrize(
    ("change", "field"),
    [
        ({"preferred_session_minutes": 14}, "preferred_session_minutes"),
        ({"preferred_session_minutes": 241}, "preferred_session_minutes"),
        ({"min_session_minutes": 46}, "min_session_minutes"),
        ({"break_minutes": -1}, "break_minutes"),
        ({"max_daily_minutes": 29}, "max_daily_minutes"),
        ({"max_daily_minutes": 1441}, "max_daily_minutes"),
        ({"min_session_minutes": 40, "max_daily_minutes": 30}, "max_daily_minutes"),
        ({"deadline_buffer_hours": 169}, "deadline_buffer_hours"),
        ({"planning_horizon_days": 0}, "planning_horizon_days"),
    ],
)
def test_invalid_preferences_rejected(
    client: TestClient, change: dict[str, int], field: str
) -> None:
    response = client.put(PREFERENCES, json=VALID_PREFERENCES | change, headers=new_user(client))
    assert list(field_errors(response)) == [field]

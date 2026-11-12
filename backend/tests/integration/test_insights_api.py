"""Dashboard and analytics figures, each traced back to records the test created."""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import StudySession, Task, WorkInterval
from app.models.enums import SessionOrigin, SessionStatus, TaskStatus
from app.services.scheduling import utc_now
from tests.integration.helpers import API, Headers, new_course, new_task, new_user

NOW = datetime(2026, 2, 4, 15, 0, tzinfo=UTC)  # Wednesday.
DASHBOARD = f"{API}/dashboard"
ANALYTICS = f"{API}/analytics"


def set_time(client: TestClient, moment: datetime) -> None:
    client.app.dependency_overrides[utc_now] = lambda: moment  # type: ignore[attr-defined]


@pytest.fixture(autouse=True)
def frozen_time(client: TestClient) -> Iterator[None]:
    set_time(client, NOW)
    yield


def dash(client: TestClient, headers: Headers) -> dict[str, Any]:
    response = client.get(DASHBOARD, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def stats(client: TestClient, headers: Headers, **params: Any) -> dict[str, Any]:
    response = client.get(ANALYTICS, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def due(days: float) -> str:
    return (NOW + timedelta(days=days)).isoformat()


def planned(
    client: TestClient, headers: Headers, task: str, start: datetime, minutes: int = 60
) -> dict[str, Any]:
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
    return response.json()


def worked(
    db: Session,
    client: TestClient,
    headers: Headers,
    task: dict[str, Any],
    start: datetime,
    end: datetime,
    status: SessionStatus = SessionStatus.COMPLETED,
) -> None:
    """Record finished work directly, because the API only allows timing the present."""
    user_id = db.get_one(Task, task["id"]).user_id
    session = StudySession(
        user_id=user_id,
        task_id=task["id"],
        start_at=start,
        end_at=end,
        status=status,
        origin=SessionOrigin.AUTO,
    )
    db.add(session)
    db.flush()
    if status == SessionStatus.COMPLETED:
        db.add(WorkInterval(user_id=user_id, session_id=session.id, started_at=start, ended_at=end))
    db.flush()


def test_new_account_gets_honest_zeros(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    body = dash(client, headers)
    assert body["today"] == []
    assert body["attention"] == []
    assert body["workload"] == []
    assert body["tasks"] == {"completed": 0, "remaining": 0, "overdue": 0}
    assert body["week"]["studied_minutes"] == 0

    data = stats(client, headers)
    assert len(data["weekly_minutes"]) == 12
    assert sum(week["minutes"] for week in data["weekly_minutes"]) == 0
    assert data["minutes_per_course"] == []
    assert data["estimates"]["tasks_compared"] == 0
    assert data["consistency"]["active_days"] == 0


@pytest.mark.parametrize("weeks", [3, 27, "many"])
def test_range_is_validated(client: TestClient, weeks: Any) -> None:
    headers = new_user(client, "UTC")
    assert client.get(ANALYTICS, params={"weeks": weeks}, headers=headers).status_code == 422


def test_other_students_data_is_never_counted(client: TestClient, db: Session) -> None:
    owner, other = new_user(client, "UTC"), new_user(client, "UTC")
    course = new_course(client, owner)
    task = new_task(client, owner, course_id=course["id"], deadline_at=due(1))
    planned(client, owner, task["id"], NOW + timedelta(hours=1))
    worked(db, client, owner, task, NOW - timedelta(hours=3), NOW - timedelta(hours=2))

    body = dash(client, other)
    assert body["today"] == [] and body["workload"] == [] and body["attention"] == []
    assert body["week"]["studied_minutes"] == 0
    assert stats(client, other)["minutes_per_course"] == []


def test_today_uses_the_students_local_day(client: TestClient, db: Session) -> None:
    # 15:00 UTC is midnight in Tokyo, so "today" there has just begun.
    headers = new_user(client, "Asia/Tokyo")
    task = new_task(client, headers, deadline_at=due(10))["id"]
    yesterday = NOW - timedelta(hours=2)
    worked(db, client, headers, {"id": task}, yesterday, yesterday + timedelta(hours=1))
    inside = planned(client, headers, task, NOW + timedelta(hours=2))
    planned(client, headers, task, NOW + timedelta(hours=25))
    assert [s["id"] for s in dash(client, headers)["today"]] == [inside["id"]]


def test_deadlines_are_split_soonest_first_and_capped(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    for days in (9, 3, 7, 5, 4, 8):
        new_task(client, headers, title=f"A{days}", deadline_at=due(days))
    new_task(client, headers, title="Quiz", task_type="quiz", deadline_at=due(2))
    new_task(client, headers, title="Undated", deadline_at=None)
    new_task(client, headers, title="Late", deadline_at=due(-1))

    body = dash(client, headers)
    assert [t["title"] for t in body["upcoming_assignments"]] == ["A3", "A4", "A5", "A7", "A8"]
    assert [t["title"] for t in body["upcoming_exams"]] == ["Quiz"]


def test_attention_explains_why(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    new_task(client, headers, title="Late", deadline_at=due(-1), estimated_minutes=30)
    new_task(client, headers, title="Unplanned", deadline_at=due(5), estimated_minutes=120)
    covered = new_task(client, headers, title="Soon", deadline_at=due(1), estimated_minutes=60)
    fine = new_task(client, headers, title="Fine", deadline_at=due(5), estimated_minutes=60)
    new_task(client, headers, title="Far", deadline_at=due(20), estimated_minutes=60)
    planned(client, headers, covered["id"], NOW + timedelta(hours=1))
    planned(client, headers, fine["id"], NOW + timedelta(hours=3))

    items = dash(client, headers)["attention"]
    assert [(i["title"], i["reason"]) for i in items] == [
        ("Late", "overdue"),
        ("Unplanned", "not_fully_planned"),
        ("Soon", "due_soon"),
    ]
    assert items[1]["unplanned_minutes"] == 120


def test_sessions_after_the_deadline_do_not_cover_it(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    task = new_task(client, headers, deadline_at=due(1), estimated_minutes=60)
    planned(client, headers, task["id"], NOW + timedelta(days=2))
    assert dash(client, headers)["attention"][0]["unplanned_minutes"] == 60


def test_task_counts_and_workload_by_course(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    algo = new_course(client, headers, name="Algorithms")
    art = new_course(client, headers, name="Art")
    new_task(client, headers, course_id=algo["id"], estimated_minutes=100, deadline_at=due(30))
    done = new_task(client, headers, course_id=algo["id"], deadline_at=due(30))
    client.post(
        f"{API}/tasks/{done['id']}/progress", json={"mark_completed": True}, headers=headers
    )
    new_task(client, headers, estimated_minutes=40, deadline_at=due(-2))

    body = dash(client, headers)
    assert body["tasks"] == {"completed": 1, "remaining": 2, "overdue": 1}
    summary = {
        w["name"]: (w["open_tasks"], w["completed_tasks"], w["remaining_minutes"])
        for w in body["workload"]
    }
    assert summary == {"Algorithms": (1, 1, 100), "Art": (0, 0, 0), "No course": (1, 0, 40)}
    assert art["id"] in [w["course_id"] for w in body["workload"]]


def test_archived_courses_leave_the_figures(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    course = new_course(client, headers)
    new_task(client, headers, course_id=course["id"], deadline_at=due(1))
    client.patch(f"{API}/courses/{course['id']}", json={"archived": True}, headers=headers)
    body = dash(client, headers)
    assert body["tasks"]["remaining"] == 0
    assert body["upcoming_assignments"] == [] and body["workload"] == []


def test_week_counts_studied_and_still_planned_time(client: TestClient, db: Session) -> None:
    headers = new_user(client, "UTC")
    task = new_task(client, headers, deadline_at=due(30), estimated_minutes=600)
    monday = datetime(2026, 2, 2, 10, 0, tzinfo=UTC)
    worked(db, client, headers, task, monday, monday + timedelta(minutes=45))
    worked(
        db,
        client,
        headers,
        task,
        monday - timedelta(hours=11),  # Sunday, so last week.
        monday - timedelta(hours=10),
    )
    planned(client, headers, task["id"], NOW + timedelta(hours=1), 30)
    planned(client, headers, task["id"], NOW + timedelta(days=7), 90)  # Next week.

    week = dash(client, headers)["week"]
    assert week["week_start"] == "2026-02-02"
    assert week["studied_minutes"] == 45
    assert week["planned_minutes"] == 30


def test_a_running_timer_counts_as_it_goes(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    task = new_task(client, headers, deadline_at=due(30))
    session = planned(client, headers, task["id"], NOW + timedelta(minutes=5))
    client.post(f"{API}/sessions/{session['id']}/start", headers=headers)
    set_time(client, NOW + timedelta(minutes=25))
    assert dash(client, headers)["week"]["studied_minutes"] == 25


def test_work_across_a_week_boundary_is_split_at_local_midnight(
    client: TestClient, db: Session
) -> None:
    headers = new_user(client, "America/Toronto")
    task = new_task(client, headers, deadline_at=due(30))
    # Sunday 23:30 to Monday 00:45 in Toronto, which is UTC-5 in February.
    worked(
        db,
        client,
        headers,
        task,
        datetime(2026, 2, 2, 4, 30, tzinfo=UTC),
        datetime(2026, 2, 2, 5, 45, tzinfo=UTC),
    )
    weeks = {w["week_start"]: w["minutes"] for w in stats(client, headers)["weekly_minutes"]}
    assert weeks["2026-01-26"] == 30
    assert weeks["2026-02-02"] == 45
    days = {d["date"]: d["minutes"] for d in stats(client, headers)["consistency"]["days"]}
    assert (days["2026-02-01"], days["2026-02-02"]) == (30, 45)


def test_the_long_day_at_the_end_of_daylight_time_counts_in_full(
    client: TestClient, db: Session
) -> None:
    moment = datetime(2026, 11, 3, 15, 0, tzinfo=UTC)
    set_time(client, moment)
    headers = new_user(client, "America/Toronto")
    task = new_task(client, headers, deadline_at="2026-12-20T00:00:00Z")
    # From 00:30 on Nov 1 to 00:30 on Nov 2 local is 25 real hours.
    start = datetime(2026, 11, 1, 4, 30, tzinfo=UTC)
    worked(db, client, headers, task, start, start + timedelta(hours=25))
    days = {d["date"]: d["minutes"] for d in stats(client, headers)["consistency"]["days"]}
    assert days["2026-11-01"] == 24 * 60 + 60 - 30
    assert days["2026-11-02"] == 30
    assert days["2026-10-31"] == 0


def test_minutes_per_course_ranked(client: TestClient, db: Session) -> None:
    headers = new_user(client, "UTC")
    algo = new_course(client, headers, name="Algorithms", color="#112233")
    art = new_course(client, headers, name="Art")
    first = new_task(client, headers, course_id=algo["id"], deadline_at=due(30))
    second = new_task(client, headers, course_id=art["id"], deadline_at=due(30))
    loose = new_task(client, headers, deadline_at=due(30))
    base = NOW - timedelta(days=1)
    worked(db, client, headers, first, base, base + timedelta(minutes=20))
    worked(
        db,
        client,
        headers,
        second,
        base + timedelta(hours=1),
        base + timedelta(hours=2),
    )
    worked(
        db,
        client,
        headers,
        loose,
        base + timedelta(hours=3),
        base + timedelta(minutes=190),
    )
    result = stats(client, headers)["minutes_per_course"]
    assert [(c["name"], c["minutes"]) for c in result] == [
        ("Art", 60),
        ("Algorithms", 20),
        ("No course", 10),
    ]
    assert result[1]["color"] == "#112233"


def test_older_work_is_outside_the_range(client: TestClient, db: Session) -> None:
    headers = new_user(client, "UTC")
    task = new_task(client, headers, deadline_at=due(30))
    start = NOW - timedelta(weeks=6)
    worked(db, client, headers, task, start, start + timedelta(hours=1))
    assert stats(client, headers, weeks=4)["minutes_per_course"] == []
    assert stats(client, headers, weeks=8)["minutes_per_course"][0]["minutes"] == 60


def _finish_task(client: TestClient, headers: Headers, task: dict[str, Any], at: datetime) -> None:
    set_time(client, at - timedelta(hours=1))
    session = planned(client, headers, task["id"], at)
    set_time(client, at)
    client.post(f"{API}/sessions/{session['id']}/start", headers=headers)
    set_time(client, at + timedelta(minutes=75))
    client.post(
        f"{API}/sessions/{session['id']}/finish",
        json={"mark_task_completed": True},
        headers=headers,
    )
    set_time(client, NOW)


def test_completions_and_estimates(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    first = new_task(client, headers, title="One", estimated_minutes=60, deadline_at=due(30))
    second = new_task(client, headers, title="Two", estimated_minutes=100, deadline_at=due(30))
    new_task(client, headers, title="Open", estimated_minutes=999, deadline_at=due(30))
    no_time = new_task(client, headers, title="NoTime", estimated_minutes=50, deadline_at=due(30))
    client.post(
        f"{API}/tasks/{no_time['id']}/progress", json={"mark_completed": True}, headers=headers
    )

    _finish_task(client, headers, first, datetime(2026, 2, 2, 10, 0, tzinfo=UTC))
    _finish_task(client, headers, second, datetime(2026, 2, 3, 10, 0, tzinfo=UTC))

    data = stats(client, headers)
    assert {c["week_start"]: c["count"] for c in data["completions"]}["2026-02-02"] == 2

    estimates = data["estimates"]
    assert estimates["tasks_compared"] == 2
    assert (estimates["estimated_minutes"], estimates["actual_minutes"]) == (160, 150)
    assert [r["title"] for r in estimates["recent"]] == ["Two", "One"]
    assert estimates["recent"][0]["actual_minutes"] == 75


def test_upcoming_covers_fourteen_local_days(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    task = new_task(client, headers, deadline_at=due(2))
    planned(client, headers, task["id"], NOW + timedelta(hours=1), 50)
    planned(client, headers, task["id"], NOW + timedelta(hours=3), 25)
    planned(client, headers, task["id"], NOW + timedelta(days=20), 25)

    upcoming = stats(client, headers)["upcoming"]
    assert len(upcoming) == 14
    assert upcoming[0] == {"date": "2026-02-04", "planned_minutes": 75, "deadlines": 0}
    assert upcoming[2]["deadlines"] == 1


def test_consistency(client: TestClient, db: Session) -> None:
    headers = new_user(client, "UTC")
    task = new_task(client, headers, deadline_at=due(30))
    for days_ago in (1, 2, 5):
        start = NOW - timedelta(days=days_ago)
        worked(db, client, headers, task, start, start + timedelta(minutes=30))
    start = NOW - timedelta(days=3)
    worked(
        db,
        client,
        headers,
        task,
        start,
        start + timedelta(minutes=30),
        SessionStatus.MISSED,
    )

    result = stats(client, headers)["consistency"]
    assert len(result["days"]) == 28
    assert result["days"][-1]["date"] == "2026-02-04"
    assert result["active_days"] == 3
    # Nothing yet today does not end the streak; it runs through yesterday and the day before.
    assert result["current_streak"] == 2
    assert (result["sessions_completed"], result["sessions_missed"]) == (3, 1)


def test_studying_today_extends_the_streak(client: TestClient, db: Session) -> None:
    headers = new_user(client, "UTC")
    task = new_task(client, headers, deadline_at=due(30))
    for days_ago in (0, 1):
        start = NOW - timedelta(days=days_ago, hours=1)
        worked(db, client, headers, task, start, start + timedelta(minutes=30))
    assert stats(client, headers)["consistency"]["current_streak"] == 2


# --- Today's progress, streak, recent sessions and the month overview ---

MONTH = f"{API}/month"
GOAL = f"{API}/preferences/daily-goal"


def month_of(client: TestClient, headers: Headers, **params: Any) -> dict[str, Any]:
    response = client.get(MONTH, params=params, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_progress_starts_empty_with_no_goal(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    assert dash(client, headers)["progress"] == {
        "studied_minutes": 0,
        "goal_minutes": None,
        "streak_days": 0,
        "studied_today": False,
    }
    assert dash(client, headers)["recent"] == []


def test_daily_goal_is_saved_without_touching_the_schedule(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    version = client.get(f"{API}/schedule/status", headers=headers).json()
    response = client.put(GOAL, json={"minutes": 120}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["daily_goal_minutes"] == 120
    assert dash(client, headers)["progress"]["goal_minutes"] == 120
    assert client.get(f"{API}/schedule/status", headers=headers).json() == version

    assert client.put(GOAL, json={"minutes": None}, headers=headers).status_code == 200
    assert dash(client, headers)["progress"]["goal_minutes"] is None


@pytest.mark.parametrize("minutes", [0, 14, 721, "lots"])
def test_daily_goal_is_validated(client: TestClient, minutes: Any) -> None:
    headers = new_user(client, "UTC")
    assert client.put(GOAL, json={"minutes": minutes}, headers=headers).status_code == 422


def test_updating_preferences_keeps_the_goal(client: TestClient) -> None:
    headers = new_user(client, "UTC")
    client.put(GOAL, json={"minutes": 90}, headers=headers)
    prefs = client.get(f"{API}/preferences", headers=headers).json()
    prefs.pop("daily_goal_minutes")
    prefs["break_minutes"] = 15
    assert client.put(f"{API}/preferences", json=prefs, headers=headers).status_code == 200
    assert client.get(f"{API}/preferences", headers=headers).json()["daily_goal_minutes"] == 90


def test_progress_counts_today_and_the_streak(client: TestClient, db: Session) -> None:
    headers = new_user(client, "UTC")
    task = new_task(client, headers, deadline_at=due(10))
    for days_ago in (3, 2, 1):  # A gap on day 4 ends the streak there.
        start = NOW - timedelta(days=days_ago)
        worked(db, client, headers, task, start, start + timedelta(minutes=30))
    worked(db, client, headers, task, NOW - timedelta(days=5), NOW - timedelta(days=5, minutes=-20))

    progress = dash(client, headers)["progress"]
    assert progress["streak_days"] == 3
    assert progress["studied_today"] is False
    assert progress["studied_minutes"] == 0

    worked(
        db, client, headers, task, NOW - timedelta(hours=2), NOW - timedelta(hours=1, minutes=15)
    )
    progress = dash(client, headers)["progress"]
    assert progress == {**progress, "streak_days": 4, "studied_today": True, "studied_minutes": 45}
    assert stats(client, headers)["consistency"]["current_streak"] == 4


def test_streak_longer_than_the_analytics_window(client: TestClient, db: Session) -> None:
    headers = new_user(client, "UTC")
    task = new_task(client, headers, deadline_at=due(10))
    for days_ago in range(1, 41):
        start = NOW - timedelta(days=days_ago)
        worked(db, client, headers, task, start, start + timedelta(minutes=10))
    assert dash(client, headers)["progress"]["streak_days"] == 40
    assert stats(client, headers)["consistency"]["current_streak"] == 40


def test_streak_uses_the_students_local_days(client: TestClient, db: Session) -> None:
    # 03:00 UTC on Wednesday is still Tuesday evening in Toronto.
    headers = new_user(client, "America/Toronto")
    task = new_task(client, headers, deadline_at=due(10))
    tuesday_night = datetime(2026, 2, 4, 3, 0, tzinfo=UTC)
    worked(db, client, headers, task, tuesday_night, tuesday_night + timedelta(minutes=30))
    progress = dash(client, headers)["progress"]
    assert progress["studied_today"] is False
    assert progress["streak_days"] == 1


def test_recent_lists_finished_sessions_newest_first(client: TestClient, db: Session) -> None:
    headers = new_user(client, "UTC")
    course = new_course(client, headers, name="Biology", color="#22aa55")
    bio = new_task(client, headers, title="Cells", course_id=course["id"], deadline_at=due(10))
    other = new_task(client, headers, title="Essay", deadline_at=due(10))
    worked(db, client, headers, bio, NOW - timedelta(days=2), NOW - timedelta(days=2, minutes=-58))
    worked(db, client, headers, other, NOW - timedelta(hours=5), NOW - timedelta(hours=4))
    worked(db, client, headers, other, NOW - timedelta(hours=1), NOW, status=SessionStatus.MISSED)

    recent = dash(client, headers)["recent"]
    assert [(r["task_title"], r["minutes"]) for r in recent] == [("Essay", 60), ("Cells", 58)]
    assert recent[1]["course_name"] == "Biology"
    assert recent[1]["course_color"] == "#22aa55"


def test_month_lists_every_day_with_study_completions_and_deadlines(
    client: TestClient, db: Session
) -> None:
    headers = new_user(client, "UTC")
    course = new_course(client, headers, color="#3366ff")
    essay = new_task(client, headers, title="Essay", course_id=course["id"], deadline_at=due(2))
    exam = new_task(client, headers, title="Midterm", task_type="midterm", deadline_at=due(3))
    worked(db, client, headers, essay, NOW - timedelta(hours=3), NOW - timedelta(hours=2))
    worked(
        db, client, headers, exam, NOW - timedelta(hours=2), NOW - timedelta(hours=1, minutes=30)
    )
    finished = db.get_one(Task, essay["id"])
    finished.status, finished.remaining_minutes = TaskStatus.COMPLETED, 0
    finished.completed_at = NOW - timedelta(minutes=30)
    db.flush()

    body = month_of(client, headers)
    assert body["month"] == "2026-02-01"
    assert len(body["days"]) == 28
    today = next(d for d in body["days"] if d["date"] == "2026-02-04")
    assert today["studied_minutes"] == 90
    assert [(t["title"], t["minutes"]) for t in today["studied"]] == [
        ("Essay", 60),
        ("Midterm", 30),
    ]
    assert today["studied"][0]["course_color"] == "#3366ff"
    assert [c["title"] for c in today["completed"]] == ["Essay"]
    friday = next(d for d in body["days"] if d["date"] == "2026-02-06")
    assert friday["deadlines"][0]["title"] == "Essay"
    assert friday["deadlines"][0]["completed"] is True
    saturday = next(d for d in body["days"] if d["date"] == "2026-02-07")
    assert saturday["deadlines"][0]["task_type"] == "midterm"


def test_month_can_be_chosen_and_splits_work_at_local_midnight(
    client: TestClient, db: Session
) -> None:
    headers = new_user(client, "America/Toronto")
    task = new_task(client, headers, deadline_at=due(10))
    # 23:30 to 00:30 Toronto time across January 31 and February 1.
    start = datetime(2026, 2, 1, 4, 30, tzinfo=UTC)
    worked(db, client, headers, task, start, start + timedelta(hours=1))
    january = month_of(client, headers, month="2026-01")
    february = month_of(client, headers, month="2026-02")
    assert len(january["days"]) == 31
    assert january["days"][-1]["studied_minutes"] == 30
    assert february["days"][0]["studied_minutes"] == 30


@pytest.mark.parametrize("value", ["2026-13", "2026-1", "0000-01", "feb", "2026-02-01"])
def test_month_is_validated(client: TestClient, value: str) -> None:
    headers = new_user(client, "UTC")
    assert client.get(MONTH, params={"month": value}, headers=headers).status_code == 422


def test_month_only_shows_the_students_own_records(client: TestClient, db: Session) -> None:
    owner = new_user(client, "UTC")
    task = new_task(client, owner, deadline_at=due(1))
    worked(db, client, owner, task, NOW - timedelta(hours=2), NOW - timedelta(hours=1))
    stranger = new_user(client, "UTC")
    days = month_of(client, stranger)["days"]
    assert all(not d["studied"] and not d["deadlines"] and not d["completed"] for d in days)


def test_month_still_shows_time_on_an_archived_course(client: TestClient, db: Session) -> None:
    headers = new_user(client, "UTC")
    course = new_course(client, headers, color="#aa3355")
    task = new_task(client, headers, title="Old lab", course_id=course["id"], deadline_at=due(1))
    worked(db, client, headers, task, NOW - timedelta(hours=2), NOW - timedelta(hours=1))
    archived = client.patch(
        f"{API}/courses/{course['id']}", json={"archived": True}, headers=headers
    )
    assert archived.status_code == 200, archived.text
    today = next(d for d in month_of(client, headers)["days"] if d["date"] == "2026-02-04")
    assert today["studied"] == [
        {"task_id": task["id"], "title": "Old lab", "course_color": "#aa3355", "minutes": 60}
    ]

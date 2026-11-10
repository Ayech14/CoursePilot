"""Proves the guarantees that are enforced by PostgreSQL itself."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.models import (
    AvailabilityWindow,
    Course,
    Notification,
    ProposalChange,
    ScheduleProposal,
    StudyPreferences,
    StudySession,
    Task,
    User,
    WorkInterval,
)
from app.models.enums import (
    ChangeAction,
    NotificationKind,
    ProposalStatus,
    ProposalTrigger,
    SessionOrigin,
    SessionStatus,
    TaskStatus,
    TaskType,
)

T0 = datetime(2026, 11, 16, 14, 0, tzinfo=UTC)


def make_user(db: Session, email: str | None = None) -> User:
    user = User(
        email=email or f"{uuid.uuid4().hex}@example.com",
        password_hash="x",
        display_name="Test",
        timezone="UTC",
    )
    db.add(user)
    db.flush()
    return user


def make_course(db: Session, user: User) -> Course:
    course = Course(user_id=user.id, name="Algorithms", color="#4f46e5")
    db.add(course)
    db.flush()
    return course


def make_task(db: Session, user: User, course: Course | None = None, **kw: Any) -> Task:
    values: dict[str, Any] = {
        "user_id": user.id,
        "course_id": course.id if course else None,
        "title": "Problem set",
        "task_type": TaskType.ASSIGNMENT,
        "estimated_minutes": 120,
        "remaining_minutes": 120,
    }
    task = Task(**(values | kw))
    db.add(task)
    db.flush()
    return task


def make_session(db: Session, task: Task, start_min: int, end_min: int, **kw: Any) -> StudySession:
    session = StudySession(
        user_id=task.user_id,
        task_id=task.id,
        start_at=T0 + timedelta(minutes=start_min),
        end_at=T0 + timedelta(minutes=end_min),
        origin=SessionOrigin.AUTO,
        **kw,
    )
    db.add(session)
    db.flush()
    return session


def test_models_and_migrations_agree(connection: Connection) -> None:
    context = MigrationContext.configure(connection)
    assert compare_metadata(context, Base.metadata) == []


# --- Overlap prevention ---------------------------------------------------------------------


def test_overlapping_sessions_rejected(db: Session) -> None:
    task = make_task(db, make_user(db))
    make_session(db, task, 0, 50)
    with pytest.raises(IntegrityError, match="excl_study_sessions_no_overlap"):
        make_session(db, task, 49, 99)


def test_contained_session_rejected(db: Session) -> None:
    task = make_task(db, make_user(db))
    make_session(db, task, 0, 120)
    with pytest.raises(IntegrityError, match="excl_study_sessions_no_overlap"):
        make_session(db, task, 30, 60)


def test_back_to_back_sessions_allowed(db: Session) -> None:
    task = make_task(db, make_user(db))
    make_session(db, task, 0, 50)
    make_session(db, task, 50, 100)


def test_overlap_rejected_across_different_tasks(db: Session) -> None:
    user = make_user(db)
    first, second = make_task(db, user), make_task(db, user)
    make_session(db, first, 0, 50)
    with pytest.raises(IntegrityError, match="excl_study_sessions_no_overlap"):
        make_session(db, second, 10, 60)


def test_different_users_can_study_at_the_same_time(db: Session) -> None:
    make_session(db, make_task(db, make_user(db)), 0, 50)
    make_session(db, make_task(db, make_user(db)), 0, 50)


@pytest.mark.parametrize(
    "status", [SessionStatus.COMPLETED, SessionStatus.MISSED, SessionStatus.CANCELLED]
)
def test_inactive_sessions_do_not_hold_their_slot(db: Session, status: SessionStatus) -> None:
    task = make_task(db, make_user(db))
    make_session(db, task, 0, 50, status=status)
    make_session(db, task, 0, 50)


def test_deferred_constraint_allows_swapping_two_sessions(db: Session) -> None:
    task = make_task(db, make_user(db))
    first, second = make_session(db, task, 0, 50), make_session(db, task, 60, 110)
    db.execute(text("SET CONSTRAINTS excl_study_sessions_no_overlap DEFERRED"))
    first.start_at, first.end_at, second.start_at, second.end_at = (
        second.start_at,
        second.end_at,
        first.start_at,
        first.end_at,
    )
    db.flush()
    db.execute(text("SET CONSTRAINTS excl_study_sessions_no_overlap IMMEDIATE"))


def test_end_must_be_after_start(db: Session) -> None:
    task = make_task(db, make_user(db))
    with pytest.raises(IntegrityError, match="ck_study_sessions_ordered"):
        make_session(db, task, 50, 50)


# --- Tenant isolation -----------------------------------------------------------------------


def test_task_cannot_reference_another_users_course(db: Session) -> None:
    owner, intruder = make_user(db), make_user(db)
    course = make_course(db, owner)
    with pytest.raises(IntegrityError, match="fk_tasks_course_owner"):
        make_task(db, intruder, course)


def test_session_cannot_reference_another_users_task(db: Session) -> None:
    owner, intruder = make_user(db), make_user(db)
    task = make_task(db, owner)
    db.add(
        StudySession(
            user_id=intruder.id,
            task_id=task.id,
            start_at=T0,
            end_at=T0 + timedelta(minutes=50),
            origin=SessionOrigin.MANUAL,
        )
    )
    with pytest.raises(IntegrityError, match="fk_study_sessions_task_owner"):
        db.flush()


def test_task_without_course_is_allowed(db: Session) -> None:
    assert make_task(db, make_user(db), task_type=TaskType.STUDY).course_id is None


# --- Availability ---------------------------------------------------------------------------


def add_window(db: Session, user: User, day: int, start: int, end: int) -> None:
    db.add(AvailabilityWindow(user_id=user.id, day_of_week=day, start_minute=start, end_minute=end))
    db.flush()


def test_overlapping_windows_on_same_day_rejected(db: Session) -> None:
    user = make_user(db)
    add_window(db, user, 0, 540, 720)
    with pytest.raises(IntegrityError, match="excl_availability_windows_no_overlap"):
        add_window(db, user, 0, 700, 800)


def test_same_hours_on_different_days_allowed(db: Session) -> None:
    user = make_user(db)
    add_window(db, user, 0, 540, 720)
    add_window(db, user, 1, 540, 720)


def test_window_can_run_to_end_of_day(db: Session) -> None:
    add_window(db, make_user(db), 6, 1200, 1440)


@pytest.mark.parametrize(("start", "end"), [(600, 600), (700, 600), (-1, 60), (1380, 1441)])
def test_invalid_window_rejected(db: Session, start: int, end: int) -> None:
    with pytest.raises(IntegrityError, match="ck_availability_windows_minute_range"):
        add_window(db, make_user(db), 0, start, end)


def test_minimum_session_cannot_exceed_preferred(db: Session) -> None:
    db.add(
        StudyPreferences(
            user_id=make_user(db).id, preferred_session_minutes=30, min_session_minutes=45
        )
    )
    with pytest.raises(IntegrityError, match="ck_study_preferences_minimum_range"):
        db.flush()


# --- Other rules ----------------------------------------------------------------------------


def test_email_must_be_lowercase(db: Session) -> None:
    with pytest.raises(IntegrityError, match="ck_users_email_lowercase"):
        make_user(db, email="Mixed@Example.com")


def test_invalid_course_color_rejected(db: Session) -> None:
    db.add(Course(user_id=make_user(db).id, name="X", color="red"))
    with pytest.raises(IntegrityError, match="ck_courses_color_hex"):
        db.flush()


def test_remaining_effort_cannot_be_negative(db: Session) -> None:
    with pytest.raises(IntegrityError, match="ck_tasks_remaining_non_negative"):
        make_task(db, make_user(db), remaining_minutes=-1)


def test_unknown_task_status_rejected_by_database(db: Session) -> None:
    task = make_task(db, make_user(db))
    with pytest.raises(IntegrityError, match="ck_tasks_task_status"):
        db.execute(text("UPDATE tasks SET status = 'nonsense' WHERE id = :id"), {"id": task.id})


def test_completed_task_requires_completion_time(db: Session) -> None:
    with pytest.raises(IntegrityError, match="ck_tasks_completed_at_matches"):
        make_task(db, make_user(db), status=TaskStatus.COMPLETED)


def test_completed_task_cannot_have_work_remaining(db: Session) -> None:
    with pytest.raises(IntegrityError, match="ck_tasks_remaining_matches_status"):
        make_task(
            db,
            make_user(db),
            status=TaskStatus.COMPLETED,
            completed_at=T0,
            remaining_minutes=30,
        )


def test_unfinished_task_must_have_work_remaining(db: Session) -> None:
    with pytest.raises(IntegrityError, match="ck_tasks_remaining_matches_status"):
        make_task(db, make_user(db), remaining_minutes=0)


def test_only_one_running_timer_per_user(db: Session) -> None:
    task = make_task(db, make_user(db))
    session = make_session(db, task, 0, 50)
    db.add(WorkInterval(user_id=task.user_id, session_id=session.id, started_at=T0))
    db.flush()
    db.add(WorkInterval(user_id=task.user_id, session_id=session.id, started_at=T0))
    with pytest.raises(IntegrityError, match="uq_work_intervals_one_running_per_user"):
        db.flush()


def make_proposal(db: Session, user: User, status: ProposalStatus) -> ScheduleProposal:
    proposal = ScheduleProposal(
        user_id=user.id,
        trigger=ProposalTrigger.GENERATE,
        status=status,
        base_schedule_version=0,
    )
    db.add(proposal)
    db.flush()
    return proposal


def test_only_one_pending_proposal_per_user(db: Session) -> None:
    user = make_user(db)
    make_proposal(db, user, ProposalStatus.PENDING)
    with pytest.raises(IntegrityError, match="uq_schedule_proposals_one_pending_per_user"):
        make_proposal(db, user, ProposalStatus.PENDING)


def test_decided_proposals_do_not_block_a_new_one(db: Session) -> None:
    user = make_user(db)
    make_proposal(db, user, ProposalStatus.APPLIED)
    make_proposal(db, user, ProposalStatus.REJECTED)
    make_proposal(db, user, ProposalStatus.PENDING)


def test_proposal_change_shape_must_match_action(db: Session) -> None:
    user = make_user(db)
    proposal, task = make_proposal(db, user, ProposalStatus.PENDING), make_task(db, user)
    db.add(
        ProposalChange(
            proposal_id=proposal.id,
            action=ChangeAction.CREATE,
            task_id=task.id,
            before_start_at=T0,
            before_end_at=T0 + timedelta(minutes=50),
        )
    )
    with pytest.raises(IntegrityError, match="ck_proposal_changes_shape_matches_action"):
        db.flush()


def test_duplicate_notification_key_rejected(db: Session) -> None:
    user = make_user(db)
    for _ in range(2):
        db.add(
            Notification(
                user_id=user.id,
                kind=NotificationKind.DEADLINE_APPROACHING,
                title="Due soon",
                body="Your task is due soon.",
                dedupe_key="deadline:abc:24h",
            )
        )
    with pytest.raises(IntegrityError, match="uq_notifications_user_id_dedupe_key"):
        db.flush()


def test_deleting_a_course_cascades_to_tasks_and_sessions(db: Session) -> None:
    user = make_user(db)
    course = make_course(db, user)
    task = make_task(db, user, course)
    session = make_session(db, task, 0, 50)
    task_id, session_id = task.id, session.id

    db.execute(text("DELETE FROM courses WHERE id = :id"), {"id": course.id})
    db.expire_all()

    assert db.get(Task, task_id) is None
    assert db.get(StudySession, session_id) is None

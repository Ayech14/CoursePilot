"""Course management and per-course progress."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Row, func, select
from sqlalchemy.orm import Session

from app.models import Course, Task, User
from app.models.enums import TaskStatus
from app.schemas.course import (
    CourseCreate,
    CourseDetail,
    CourseProgress,
    CourseRead,
    CourseUpdate,
)
from app.schemas.task import TaskRead
from app.services.common import get_owned, mark_schedule_inputs_changed

_UPCOMING_LIMIT = 10


def _progress_rows(db: Session, user_id: uuid.UUID) -> dict[uuid.UUID, Row[tuple[object, ...]]]:
    """One aggregate query for all courses, so listing does not run a query per course."""
    is_open = Task.status != TaskStatus.COMPLETED
    now = datetime.now(UTC)
    rows = db.execute(
        select(
            Task.course_id,
            func.count().label("total_tasks"),
            func.count().filter(Task.status == TaskStatus.COMPLETED).label("completed_tasks"),
            func.sum(Task.estimated_minutes).label("estimated_minutes"),
            func.sum(Task.remaining_minutes).label("remaining_minutes"),
            func.sum(Task.actual_minutes).label("actual_minutes"),
            func.min(Task.deadline_at)
            .filter(is_open, Task.deadline_at >= now)
            .label("next_deadline_at"),
        )
        .where(Task.user_id == user_id, Task.course_id.is_not(None))
        .group_by(Task.course_id)
    ).all()
    return {row.course_id: row for row in rows}  # type: ignore[misc]


def _to_read[R: CourseRead](
    course: Course, rows: dict[uuid.UUID, Row[tuple[object, ...]]], schema: type[R], **extra: Any
) -> R:
    row = rows.get(course.id)
    progress = CourseProgress.model_validate(row._asdict()) if row else CourseProgress()
    fields: dict[str, Any] = {
        name: getattr(course, name) for name in CourseRead.model_fields if name != "progress"
    }
    return schema(**fields, progress=progress, **extra)


def list_courses(db: Session, user: User, include_archived: bool) -> list[CourseRead]:
    query = select(Course).where(Course.user_id == user.id).order_by(Course.name, Course.id)
    if not include_archived:
        query = query.where(Course.archived_at.is_(None))
    rows = _progress_rows(db, user.id)
    return [_to_read(course, rows, CourseRead) for course in db.scalars(query)]


def get_course(db: Session, user: User, course_id: uuid.UUID) -> CourseDetail:
    course = get_owned(db, Course, course_id, user.id)
    upcoming = db.scalars(
        select(Task)
        .where(
            Task.user_id == user.id,
            Task.course_id == course.id,
            Task.status != TaskStatus.COMPLETED,
            Task.deadline_at.is_not(None),
        )
        .order_by(Task.deadline_at, Task.id)
        .limit(_UPCOMING_LIMIT)
    )
    return _to_read(
        course,
        _progress_rows(db, user.id),
        CourseDetail,
        upcoming_tasks=[TaskRead.model_validate(task) for task in upcoming],
    )


def create_course(db: Session, user: User, data: CourseCreate) -> CourseRead:
    course = Course(user_id=user.id, **data.model_dump())
    db.add(course)
    db.commit()
    return _to_read(course, {}, CourseRead)


def update_course(
    db: Session, user: User, course_id: uuid.UUID, changes: CourseUpdate
) -> CourseRead:
    course = get_owned(db, Course, course_id, user.id)
    values = changes.model_dump(exclude_unset=True)

    archived = values.pop("archived", None)
    if archived is not None:
        mark_schedule_inputs_changed(db, user.id)
    if archived is False:
        course.archived_at = None
    elif archived and course.archived_at is None:
        course.archived_at = datetime.now(UTC)

    for field, value in values.items():
        setattr(course, field, value)
    db.commit()
    return _to_read(course, _progress_rows(db, user.id), CourseRead)


def delete_course(db: Session, user: User, course_id: uuid.UUID) -> None:
    """Delete a course. The database cascades to its tasks and their sessions."""
    db.delete(get_owned(db, Course, course_id, user.id))
    mark_schedule_inputs_changed(db, user.id)
    db.commit()

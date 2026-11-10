"""Task management and progress tracking.

Status and remaining effort must always agree: a task is completed exactly when no work remains.
The transitions below keep that true, and a database CHECK constraint backs them up.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import CourseArchivedError, InvalidFieldsError, TaskCompletedError
from app.models import Course, Task, User
from app.models.enums import TaskStatus, TaskType
from app.schemas.common import Page
from app.schemas.task import TaskCreate, TaskProgress, TaskRead, TaskUpdate
from app.services.common import get_owned, mark_schedule_inputs_changed

_EXAM_TYPES = frozenset({TaskType.MIDTERM, TaskType.FINAL_EXAM, TaskType.QUIZ})

# Work assumed to be left on an unfinished task whose effort would otherwise compute as zero.
MINIMUM_UNFINISHED_MINUTES = 15


@dataclass(frozen=True)
class TaskFilters:
    course_id: uuid.UUID | None = None
    statuses: list[TaskStatus] | None = None
    task_type: TaskType | None = None
    due_after: datetime | None = None
    due_before: datetime | None = None
    limit: int = 100
    offset: int = 0


def _check_course(db: Session, user: User, course_id: uuid.UUID) -> None:
    course = db.scalar(select(Course).where(Course.id == course_id, Course.user_id == user.id))
    if course is None:
        raise InvalidFieldsError({"course_id": "Course not found."})
    if course.archived_at is not None:
        raise CourseArchivedError


def _check_exam_has_date(task: Task) -> None:
    if task.task_type in _EXAM_TYPES and task.deadline_at is None:
        raise InvalidFieldsError({"deadline_at": "An exam or quiz needs a date."})


def _complete(task: Task) -> None:
    task.status = TaskStatus.COMPLETED
    task.remaining_minutes = 0
    task.completed_at = task.completed_at or datetime.now(UTC)


def list_tasks(db: Session, user: User, filters: TaskFilters) -> Page[TaskRead]:
    conditions = [Task.user_id == user.id]
    if filters.course_id is not None:
        conditions.append(Task.course_id == filters.course_id)
    if filters.statuses:
        conditions.append(Task.status.in_(filters.statuses))
    if filters.task_type is not None:
        conditions.append(Task.task_type == filters.task_type)
    if filters.due_after is not None:
        conditions.append(Task.deadline_at >= filters.due_after)
    if filters.due_before is not None:
        conditions.append(Task.deadline_at <= filters.due_before)

    total = db.scalar(select(func.count()).select_from(Task).where(*conditions)) or 0
    tasks = db.scalars(
        select(Task)
        .where(*conditions)
        .order_by(Task.deadline_at.asc().nulls_last(), Task.created_at, Task.id)
        .limit(filters.limit)
        .offset(filters.offset)
    )
    return Page(items=[TaskRead.model_validate(task) for task in tasks], total=total)


def get_task(db: Session, user: User, task_id: uuid.UUID) -> Task:
    return get_owned(db, Task, task_id, user.id)


def create_task(db: Session, user: User, data: TaskCreate) -> Task:
    if data.course_id is not None:
        _check_course(db, user, data.course_id)

    values = data.model_dump()
    if values["remaining_minutes"] is None:
        values["remaining_minutes"] = data.estimated_minutes
    task = Task(user_id=user.id, **values)
    _check_exam_has_date(task)

    db.add(task)
    mark_schedule_inputs_changed(db, user.id)
    db.commit()
    return task


def update_task(db: Session, user: User, task_id: uuid.UUID, changes: TaskUpdate) -> Task:
    task = get_owned(db, Task, task_id, user.id)
    values = changes.model_dump(exclude_unset=True)
    status: TaskStatus | None = values.pop("status", None)
    remaining: int | None = values.pop("remaining_minutes", None)

    if values.get("course_id") is not None and values["course_id"] != task.course_id:
        _check_course(db, user, values["course_id"])

    for field, value in values.items():
        setattr(task, field, value)
    _check_exam_has_date(task)
    _apply_state_change(task, status, remaining)

    mark_schedule_inputs_changed(db, user.id)
    db.commit()
    return task


def _apply_state_change(task: Task, status: TaskStatus | None, remaining: int | None) -> None:
    if status == TaskStatus.COMPLETED and remaining:
        raise InvalidFieldsError({"remaining_minutes": "A completed task has no work remaining."})
    if status not in (None, TaskStatus.COMPLETED) and remaining == 0:
        raise InvalidFieldsError({"remaining_minutes": "An unfinished task needs work remaining."})

    if status == TaskStatus.COMPLETED or remaining == 0:
        _complete(task)
        return
    if status is None and remaining is None:
        return

    reopening = task.status == TaskStatus.COMPLETED
    if remaining is not None:
        task.remaining_minutes = remaining
    elif reopening:
        task.remaining_minutes = max(
            task.estimated_minutes - task.actual_minutes, MINIMUM_UNFINISHED_MINUTES
        )

    if status is not None:
        task.status = status
    elif reopening:
        task.status = TaskStatus.IN_PROGRESS if task.actual_minutes else TaskStatus.TODO
    task.completed_at = None


def record_progress(db: Session, user: User, task_id: uuid.UUID, progress: TaskProgress) -> Task:
    task = get_owned(db, Task, task_id, user.id)
    if task.status == TaskStatus.COMPLETED:
        raise TaskCompletedError
    if (
        progress.minutes_spent is None
        and progress.remaining_minutes is None
        and not progress.mark_completed
    ):
        raise InvalidFieldsError(
            {"minutes_spent": "Enter time spent or time remaining, or mark the task complete."}
        )

    if progress.minutes_spent:
        task.actual_minutes += progress.minutes_spent

    if progress.mark_completed or progress.remaining_minutes == 0:
        _complete(task)
    else:
        if progress.remaining_minutes is not None:
            task.remaining_minutes = progress.remaining_minutes
        elif progress.minutes_spent:
            # Spending the estimate does not mean the work is done. Only the student decides that.
            task.remaining_minutes = max(
                task.remaining_minutes - progress.minutes_spent, MINIMUM_UNFINISHED_MINUTES
            )
        task.status = TaskStatus.IN_PROGRESS

    mark_schedule_inputs_changed(db, user.id)
    db.commit()
    return task


def delete_task(db: Session, user: User, task_id: uuid.UUID) -> None:
    db.delete(get_owned(db, Task, task_id, user.id))
    mark_schedule_inputs_changed(db, user.id)
    db.commit()

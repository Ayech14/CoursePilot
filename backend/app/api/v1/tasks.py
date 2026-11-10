"""Task endpoints."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status
from pydantic import AwareDatetime

from app.api.deps import CurrentUser, DbSession
from app.models.enums import TaskStatus, TaskType
from app.schemas.common import Page
from app.schemas.task import TaskCreate, TaskProgress, TaskRead, TaskUpdate
from app.services import tasks as service

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("")
def list_tasks(
    user: CurrentUser,
    db: DbSession,
    course_id: uuid.UUID | None = None,
    task_status: Annotated[list[TaskStatus] | None, Query(alias="status")] = None,
    task_type: TaskType | None = None,
    due_after: AwareDatetime | None = None,
    due_before: AwareDatetime | None = None,
    limit: Annotated[int, Query(ge=1, le=500)] = 100,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> Page[TaskRead]:
    filters = service.TaskFilters(
        course_id, task_status, task_type, due_after, due_before, limit, offset
    )
    return service.list_tasks(db, user, filters)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_task(data: TaskCreate, user: CurrentUser, db: DbSession) -> TaskRead:
    return TaskRead.model_validate(service.create_task(db, user, data))


@router.get("/{task_id}")
def get_task(task_id: uuid.UUID, user: CurrentUser, db: DbSession) -> TaskRead:
    return TaskRead.model_validate(service.get_task(db, user, task_id))


@router.patch("/{task_id}")
def update_task(
    task_id: uuid.UUID, changes: TaskUpdate, user: CurrentUser, db: DbSession
) -> TaskRead:
    return TaskRead.model_validate(service.update_task(db, user, task_id, changes))


@router.post("/{task_id}/progress")
def record_progress(
    task_id: uuid.UUID, progress: TaskProgress, user: CurrentUser, db: DbSession
) -> TaskRead:
    return TaskRead.model_validate(service.record_progress(db, user, task_id, progress))


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    service.delete_task(db, user, task_id)

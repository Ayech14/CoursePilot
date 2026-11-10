"""Course endpoints."""

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.schemas.course import CourseCreate, CourseDetail, CourseRead, CourseUpdate
from app.services import courses as service

router = APIRouter(prefix="/courses", tags=["courses"])


@router.get("")
def list_courses(
    user: CurrentUser, db: DbSession, include_archived: bool = False
) -> list[CourseRead]:
    return service.list_courses(db, user, include_archived)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_course(data: CourseCreate, user: CurrentUser, db: DbSession) -> CourseRead:
    return service.create_course(db, user, data)


@router.get("/{course_id}")
def get_course(course_id: uuid.UUID, user: CurrentUser, db: DbSession) -> CourseDetail:
    return service.get_course(db, user, course_id)


@router.patch("/{course_id}")
def update_course(
    course_id: uuid.UUID, changes: CourseUpdate, user: CurrentUser, db: DbSession
) -> CourseRead:
    return service.update_course(db, user, course_id, changes)


@router.delete("/{course_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_course(course_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    service.delete_course(db, user, course_id)

"""Manual control of individual study sessions."""

import logging
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import (
    InvalidFieldsError,
    PlacementWarningsError,
    SessionConflictError,
    SessionNotEditableError,
)
from app.models import Course, StudySession, Task, User
from app.models.enums import SessionOrigin, SessionStatus, TaskStatus
from app.schemas.schedule import (
    ConflictRead,
    PlacementQuery,
    PlacementRead,
    SessionCreate,
    SessionRead,
    SessionUpdate,
    SlotRead,
    WarningRead,
)
from app.services.common import get_owned, mark_schedule_inputs_changed
from app.services.scheduling import (
    active_future_sessions,
    build_request,
    lock_user,
    session_read,
)
from scheduler.explain import describe_conflict, describe_warning
from scheduler.models import PlanRequest
from scheduler.placement import check_placement, suggest_slots

logger = logging.getLogger(__name__)


def _evaluate(
    request: PlanRequest,
    task_id: uuid.UUID,
    start: datetime,
    end: datetime,
    session_id: uuid.UUID | None,
) -> PlacementRead:
    ignoring = None if session_id is None else str(session_id)
    result = check_placement(request, str(task_id), start, end, ignoring)
    alternatives = (
        []
        if result.ok
        else [
            SlotRead(start_at=slot.start, end_at=slot.end)
            for slot in suggest_slots(
                request,
                str(task_id),
                int((end - start).total_seconds() // 60),
                start,
                ignoring,
            )
        ]
    )
    return PlacementRead(
        ok=result.ok,
        conflicts=[
            ConflictRead(
                kind=conflict.kind.value,
                message=describe_conflict(conflict.kind),
                session_id=None if conflict.session_id is None else uuid.UUID(conflict.session_id),
            )
            for conflict in result.conflicts
        ],
        warnings=[
            WarningRead(kind=warning.value, message=describe_warning(warning))
            for warning in result.warnings
        ],
        alternatives=alternatives,
    )


def _enforce(evaluation: PlacementRead, *, acknowledged: bool) -> None:
    """Overlap is always refused. Anything else needs only the student's confirmation."""
    details: dict[str, Any] = evaluation.model_dump(mode="json")
    if evaluation.conflicts:
        raise SessionConflictError(details=details)
    if evaluation.warnings and not acknowledged:
        raise PlacementWarningsError(details=details)


def _request_for(db: Session, user: User, now: datetime) -> PlanRequest:
    return build_request(db, user, now, active_future_sessions(db, user, now))


def _read(db: Session, session: StudySession) -> SessionRead:
    task = db.get_one(Task, session.task_id)
    course = None if task.course_id is None else db.get(Course, task.course_id)
    return session_read(session, task, course)


def check(db: Session, user: User, query: PlacementQuery, now: datetime) -> PlacementRead:
    """Evaluate a time without saving anything."""
    task_id = query.task_id
    if query.session_id is not None:
        task_id = get_owned(db, StudySession, query.session_id, user.id).task_id
    if task_id is None:
        raise InvalidFieldsError({"task_id": "Choose a task or a session."})
    get_owned(db, Task, task_id, user.id)
    return _evaluate(
        _request_for(db, user, now), task_id, query.start_at, query.end_at, query.session_id
    )


def create_session(db: Session, user: User, data: SessionCreate, now: datetime) -> SessionRead:
    locked = lock_user(db, user)
    task = db.scalar(select(Task).where(Task.id == data.task_id, Task.user_id == locked.id))
    if task is None:
        raise InvalidFieldsError({"task_id": "Task not found."})
    if task.status == TaskStatus.COMPLETED:
        raise InvalidFieldsError({"task_id": "This task is already completed."})

    evaluation = _evaluate(_request_for(db, locked, now), task.id, data.start_at, data.end_at, None)
    _enforce(evaluation, acknowledged=data.acknowledge_warnings)

    session = StudySession(
        user_id=locked.id,
        task_id=task.id,
        start_at=data.start_at,
        end_at=data.end_at,
        origin=SessionOrigin.MANUAL,
    )
    db.add(session)
    mark_schedule_inputs_changed(db, locked.id)
    db.commit()
    return _read(db, session)


def _editable(db: Session, user: User, session_id: uuid.UUID) -> StudySession:
    session = get_owned(db, StudySession, session_id, user.id)
    if session.status != SessionStatus.PLANNED:
        raise SessionNotEditableError
    return session


def update_session(
    db: Session, user: User, session_id: uuid.UUID, data: SessionUpdate, now: datetime
) -> SessionRead:
    """Move or resize a session. It then counts as the student's own and is kept when possible."""
    locked = lock_user(db, user)
    session = _editable(db, locked, session_id)

    evaluation = _evaluate(
        _request_for(db, locked, now), session.task_id, data.start_at, data.end_at, session.id
    )
    _enforce(evaluation, acknowledged=data.acknowledge_warnings)

    session.start_at = data.start_at
    session.end_at = data.end_at
    session.user_modified_at = now
    session.explanation = None
    mark_schedule_inputs_changed(db, locked.id)
    db.commit()
    logger.info("session_moved", extra={"user_id": str(locked.id), "session_id": str(session.id)})
    return _read(db, session)


def set_locked(db: Session, user: User, session_id: uuid.UUID, *, locked: bool) -> SessionRead:
    session = _editable(db, user, session_id)
    session.is_locked = locked
    mark_schedule_inputs_changed(db, user.id)
    db.commit()
    return _read(db, session)


def delete_session(db: Session, user: User, session_id: uuid.UUID) -> None:
    """Cancel a session. Its time returns to the task as work still to be planned."""
    session = _editable(db, user, session_id)
    session.status = SessionStatus.CANCELLED
    mark_schedule_inputs_changed(db, user.id)
    db.commit()

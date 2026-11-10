"""Schedule preview, apply and session endpoints."""

import uuid
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import AwareDatetime

from app.api.deps import CurrentUser, DbSession
from app.schemas.schedule import (
    ApplyRequest,
    ApplyResult,
    PlacementQuery,
    PlacementRead,
    PreviewRequest,
    ProposalRead,
    ScheduleStatus,
    SessionCreate,
    SessionRead,
    SessionUpdate,
)
from app.services import scheduling as service
from app.services import sessions as session_service

router = APIRouter(prefix="/schedule", tags=["schedule"])
sessions_router = APIRouter(prefix="/sessions", tags=["schedule"])

_DEFAULT_RANGE = timedelta(days=30)

# A dependency, so that tests can fix the time and get exactly reproducible schedules.
Now = Annotated[datetime, Depends(service.utc_now)]


@router.post("/preview", status_code=status.HTTP_201_CREATED)
def preview(
    user: CurrentUser, db: DbSession, now: Now, options: PreviewRequest = PreviewRequest()
) -> ProposalRead:
    return service.create_preview(db, user, now, options.mode)


@router.get("/status")
def schedule_status(user: CurrentUser, db: DbSession, now: Now) -> ScheduleStatus:
    return service.get_status(db, user, now)


@router.get("/proposals/current")
def current_proposal(user: CurrentUser, db: DbSession) -> ProposalRead | None:
    return service.get_pending_proposal(db, user)


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ProposalRead:
    return service.get_proposal(db, user, proposal_id)


@router.post("/proposals/{proposal_id}/apply")
def apply_proposal(
    proposal_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    now: Now,
    choices: ApplyRequest = ApplyRequest(),
) -> ApplyResult:
    return service.apply_proposal(db, user, proposal_id, choices, now)


@router.post("/proposals/{proposal_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject_proposal(proposal_id: uuid.UUID, user: CurrentUser, db: DbSession, now: Now) -> None:
    service.reject_proposal(db, user, proposal_id, now)


@sessions_router.get("")
def list_sessions(
    user: CurrentUser,
    db: DbSession,
    now: Now,
    start: AwareDatetime | None = None,
    end: AwareDatetime | None = None,
) -> list[SessionRead]:
    range_start = start or now
    return service.list_sessions(db, user, now, range_start, end or range_start + _DEFAULT_RANGE)


@sessions_router.post("", status_code=status.HTTP_201_CREATED)
def create_session(data: SessionCreate, user: CurrentUser, db: DbSession, now: Now) -> SessionRead:
    return session_service.create_session(db, user, data, now)


@sessions_router.post("/check-placement")
def check_placement(
    query: PlacementQuery, user: CurrentUser, db: DbSession, now: Now
) -> PlacementRead:
    return session_service.check(db, user, query, now)


@sessions_router.patch("/{session_id}")
def update_session(
    session_id: uuid.UUID, data: SessionUpdate, user: CurrentUser, db: DbSession, now: Now
) -> SessionRead:
    return session_service.update_session(db, user, session_id, data, now)


@sessions_router.post("/{session_id}/lock")
def lock_session(session_id: uuid.UUID, user: CurrentUser, db: DbSession) -> SessionRead:
    return session_service.set_locked(db, user, session_id, locked=True)


@sessions_router.post("/{session_id}/unlock")
def unlock_session(session_id: uuid.UUID, user: CurrentUser, db: DbSession) -> SessionRead:
    return session_service.set_locked(db, user, session_id, locked=False)


@sessions_router.delete("/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    session_service.delete_session(db, user, session_id)

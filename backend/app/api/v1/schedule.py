"""Schedule preview, apply and session endpoints."""

import uuid
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, status
from pydantic import AwareDatetime

from app.api.deps import CurrentUser, DbSession
from app.schemas.schedule import ApplyResult, ProposalRead, SessionRead
from app.services import scheduling as service

router = APIRouter(prefix="/schedule", tags=["schedule"])
sessions_router = APIRouter(prefix="/sessions", tags=["schedule"])

_DEFAULT_RANGE = timedelta(days=30)

# A dependency, so that tests can fix the time and get exactly reproducible schedules.
Now = Annotated[datetime, Depends(service.utc_now)]


@router.post("/preview", status_code=status.HTTP_201_CREATED)
def preview(user: CurrentUser, db: DbSession, now: Now) -> ProposalRead:
    return service.create_preview(db, user, now)


@router.get("/proposals/current")
def current_proposal(user: CurrentUser, db: DbSession) -> ProposalRead | None:
    return service.get_pending_proposal(db, user)


@router.get("/proposals/{proposal_id}")
def get_proposal(proposal_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ProposalRead:
    return service.get_proposal(db, user, proposal_id)


@router.post("/proposals/{proposal_id}/apply")
def apply_proposal(
    proposal_id: uuid.UUID, user: CurrentUser, db: DbSession, now: Now
) -> ApplyResult:
    return service.apply_proposal(db, user, proposal_id, now)


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
    return service.list_sessions(db, user, range_start, end or range_start + _DEFAULT_RANGE)

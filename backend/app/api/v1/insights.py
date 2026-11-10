"""Dashboard and analytics endpoints."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.api.v1.schedule import Now
from app.schemas.insights import AnalyticsRead, DashboardRead
from app.services import insights as service

router = APIRouter(tags=["insights"])


@router.get("/dashboard")
def dashboard(user: CurrentUser, db: DbSession, now: Now) -> DashboardRead:
    return service.dashboard(db, user, now)


@router.get("/analytics")
def analytics(
    user: CurrentUser,
    db: DbSession,
    now: Now,
    weeks: Annotated[int, Query(ge=4, le=26)] = 12,
) -> AnalyticsRead:
    return service.analytics(db, user, now, weeks)

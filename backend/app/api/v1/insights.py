"""Dashboard and analytics endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import CurrentUser, DbSession
from app.api.v1.schedule import Now
from app.schemas.insights import AnalyticsRead, DashboardRead, MonthRead
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


@router.get("/month")
def month(
    user: CurrentUser,
    db: DbSession,
    now: Now,
    month: Annotated[
        str | None, Query(pattern=r"^(19|20)\d{2}-(0[1-9]|1[0-2])$", description="YYYY-MM")
    ] = None,
) -> MonthRead:
    first = None if month is None else date.fromisoformat(f"{month}-01")
    return service.month(db, user, now, first)

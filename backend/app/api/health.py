"""Health probes for orchestrators and uptime checks."""

from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.api.deps import DbSession
from app.core.errors import ServiceUnavailableError

router = APIRouter(prefix="/health", tags=["health"])


@router.get("")
def liveness() -> dict[str, str]:
    """The process is running."""
    return {"status": "ok"}


@router.get("/ready")
def readiness(db: DbSession) -> dict[str, str]:
    """The process can reach its database."""
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise ServiceUnavailableError from exc
    return {"status": "ready"}

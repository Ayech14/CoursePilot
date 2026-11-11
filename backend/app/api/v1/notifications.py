"""In-app notifications."""

import uuid

from fastapi import APIRouter, status

from app.api.deps import CurrentUser, DbSession
from app.api.v1.schedule import Now
from app.schemas.notification import NotificationList, NotificationRead
from app.services import notifications as service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
def list_notifications(user: CurrentUser, db: DbSession, now: Now) -> NotificationList:
    """The latest notifications, newest first. Works out any new ones before answering."""
    return service.list_notifications(db, user, now)


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(user: CurrentUser, db: DbSession, now: Now) -> None:
    service.mark_all_read(db, user, now)


@router.post("/{notification_id}/read")
def mark_read(
    notification_id: uuid.UUID, user: CurrentUser, db: DbSession, now: Now
) -> NotificationRead:
    return service.mark_read(db, user, notification_id, now)

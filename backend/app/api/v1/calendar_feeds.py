"""Connected calendars, deadline suggestions and combined busy time."""

import uuid

from fastapi import APIRouter, status
from pydantic import AwareDatetime

from app.api.deps import CurrentUser, DbSession
from app.api.v1.schedule import Now
from app.schemas.calendar import (
    BusyRead,
    FeedCreate,
    FeedRead,
    FeedUpdate,
    SuggestionAccept,
    SuggestionRead,
)
from app.schemas.task import TaskRead
from app.services import calendar_feeds as service
from app.services.tasks import get_task

router = APIRouter(prefix="/calendar-feeds", tags=["calendars"])
suggestions_router = APIRouter(prefix="/deadline-suggestions", tags=["calendars"])
busy_router = APIRouter(prefix="/busy-times", tags=["calendars"])


@router.get("")
def list_feeds(user: CurrentUser, db: DbSession) -> list[FeedRead]:
    return service.list_feeds(db, user)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_feed(data: FeedCreate, user: CurrentUser, db: DbSession, now: Now) -> FeedRead:
    return service.create_feed(db, user, data, now)


@router.post("/sync-stale")
def sync_stale(user: CurrentUser, db: DbSession, now: Now) -> list[FeedRead]:
    return service.sync_stale(db, user, now)


@router.patch("/{feed_id}")
def rename_feed(feed_id: uuid.UUID, data: FeedUpdate, user: CurrentUser, db: DbSession) -> FeedRead:
    return service.rename_feed(db, user, feed_id, data.name)


@router.post("/{feed_id}/sync")
def sync_feed(feed_id: uuid.UUID, user: CurrentUser, db: DbSession, now: Now) -> FeedRead:
    return service.sync_feed(db, user, feed_id, now)


@router.delete("/{feed_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_feed(feed_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    service.delete_feed(db, user, feed_id)


@suggestions_router.get("")
def list_suggestions(user: CurrentUser, db: DbSession, now: Now) -> list[SuggestionRead]:
    return service.list_suggestions(db, user, now)


@suggestions_router.post("/{suggestion_id}/accept", status_code=status.HTTP_201_CREATED)
def accept_suggestion(
    suggestion_id: uuid.UUID, choice: SuggestionAccept, user: CurrentUser, db: DbSession
) -> TaskRead:
    task_id = service.accept_suggestion(db, user, suggestion_id, choice)
    return TaskRead.model_validate(get_task(db, user, task_id))


@suggestions_router.post("/{suggestion_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
def dismiss_suggestion(suggestion_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    service.dismiss_suggestion(db, user, suggestion_id)


@busy_router.get("")
def list_busy(
    start: AwareDatetime, end: AwareDatetime, user: CurrentUser, db: DbSession
) -> list[BusyRead]:
    return service.list_busy(db, user, start, end)

"""Availability and study preference endpoints."""

import uuid

from fastapi import APIRouter, status
from pydantic import AwareDatetime

from app.api.deps import CurrentUser, DbSession
from app.schemas.availability import (
    OneOffBlockRead,
    OneOffBlockWrite,
    PreferencesRead,
    PreferencesWrite,
    RecurringBlockRead,
    RecurringBlockWrite,
    WindowRead,
    WindowsReplace,
)
from app.services import availability as service

router = APIRouter(prefix="/availability", tags=["availability"])
preferences_router = APIRouter(prefix="/preferences", tags=["availability"])


@router.get("/windows")
def list_windows(user: CurrentUser, db: DbSession) -> list[WindowRead]:
    return [WindowRead.model_validate(w) for w in service.list_windows(db, user)]


@router.put("/windows")
def replace_windows(data: WindowsReplace, user: CurrentUser, db: DbSession) -> list[WindowRead]:
    saved = service.replace_windows(db, user, list(data.windows))
    return [WindowRead.model_validate(w) for w in saved]


@router.get("/recurring-blocks")
def list_recurring_blocks(user: CurrentUser, db: DbSession) -> list[RecurringBlockRead]:
    return [RecurringBlockRead.model_validate(b) for b in service.list_recurring_blocks(db, user)]


@router.post("/recurring-blocks", status_code=status.HTTP_201_CREATED)
def create_recurring_block(
    data: RecurringBlockWrite, user: CurrentUser, db: DbSession
) -> RecurringBlockRead:
    return RecurringBlockRead.model_validate(service.create_recurring_block(db, user, data))


@router.put("/recurring-blocks/{block_id}")
def update_recurring_block(
    block_id: uuid.UUID, data: RecurringBlockWrite, user: CurrentUser, db: DbSession
) -> RecurringBlockRead:
    return RecurringBlockRead.model_validate(
        service.update_recurring_block(db, user, block_id, data)
    )


@router.delete("/recurring-blocks/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_recurring_block(block_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    service.delete_recurring_block(db, user, block_id)


@router.get("/one-off-blocks")
def list_one_off_blocks(
    user: CurrentUser,
    db: DbSession,
    ends_after: AwareDatetime | None = None,
    starts_before: AwareDatetime | None = None,
) -> list[OneOffBlockRead]:
    blocks = service.list_one_off_blocks(db, user, ends_after, starts_before)
    return [OneOffBlockRead.model_validate(b) for b in blocks]


@router.post("/one-off-blocks", status_code=status.HTTP_201_CREATED)
def create_one_off_block(
    data: OneOffBlockWrite, user: CurrentUser, db: DbSession
) -> OneOffBlockRead:
    return OneOffBlockRead.model_validate(service.create_one_off_block(db, user, data))


@router.put("/one-off-blocks/{block_id}")
def update_one_off_block(
    block_id: uuid.UUID, data: OneOffBlockWrite, user: CurrentUser, db: DbSession
) -> OneOffBlockRead:
    return OneOffBlockRead.model_validate(service.update_one_off_block(db, user, block_id, data))


@router.delete("/one-off-blocks/{block_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_one_off_block(block_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    service.delete_one_off_block(db, user, block_id)


@preferences_router.get("")
def get_preferences(user: CurrentUser, db: DbSession) -> PreferencesRead:
    return PreferencesRead.model_validate(service.get_preferences(db, user))


@preferences_router.put("")
def update_preferences(data: PreferencesWrite, user: CurrentUser, db: DbSession) -> PreferencesRead:
    return PreferencesRead.model_validate(service.update_preferences(db, user, data))

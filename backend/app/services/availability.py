"""Weekly availability, unavailable time and study preferences."""

import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.errors import InvalidFieldsError
from app.models import (
    AvailabilityWindow,
    OneOffBlock,
    RecurringBlock,
    StudyPreferences,
    User,
)
from app.schemas.availability import (
    OneOffBlockWrite,
    PreferencesWrite,
    RecurringBlockWrite,
    WeeklyTime,
)
from app.services.common import get_owned


def list_windows(db: Session, user: User) -> list[AvailabilityWindow]:
    return list(
        db.scalars(
            select(AvailabilityWindow)
            .where(AvailabilityWindow.user_id == user.id)
            .order_by(AvailabilityWindow.day_of_week, AvailabilityWindow.start_minute)
        )
    )


def _check_no_overlaps(windows: list[WeeklyTime]) -> None:
    ordered = sorted(enumerate(windows), key=lambda w: (w[1].day_of_week, w[1].start_minute))
    errors = {
        f"windows.{index}": "Overlaps another time range on this day."
        for (_, previous), (index, current) in zip(ordered, ordered[1:], strict=False)
        if previous.day_of_week == current.day_of_week
        and current.start_minute < previous.end_minute
    }
    if errors:
        raise InvalidFieldsError(errors)


def replace_windows(db: Session, user: User, windows: list[WeeklyTime]) -> list[AvailabilityWindow]:
    """Replace the whole week at once, which is how the weekly editor saves."""
    _check_no_overlaps(windows)
    db.execute(delete(AvailabilityWindow).where(AvailabilityWindow.user_id == user.id))
    db.add_all(AvailabilityWindow(user_id=user.id, **window.model_dump()) for window in windows)
    db.commit()
    return list_windows(db, user)


def list_recurring_blocks(db: Session, user: User) -> list[RecurringBlock]:
    return list(
        db.scalars(
            select(RecurringBlock)
            .where(RecurringBlock.user_id == user.id)
            .order_by(RecurringBlock.day_of_week, RecurringBlock.start_minute, RecurringBlock.id)
        )
    )


def create_recurring_block(db: Session, user: User, data: RecurringBlockWrite) -> RecurringBlock:
    block = RecurringBlock(user_id=user.id, **data.model_dump())
    db.add(block)
    db.commit()
    return block


def update_recurring_block(
    db: Session, user: User, block_id: uuid.UUID, data: RecurringBlockWrite
) -> RecurringBlock:
    block = get_owned(db, RecurringBlock, block_id, user.id)
    for field, value in data.model_dump().items():
        setattr(block, field, value)
    db.commit()
    return block


def delete_recurring_block(db: Session, user: User, block_id: uuid.UUID) -> None:
    db.delete(get_owned(db, RecurringBlock, block_id, user.id))
    db.commit()


def list_one_off_blocks(
    db: Session, user: User, ends_after: datetime | None, starts_before: datetime | None
) -> list[OneOffBlock]:
    query = select(OneOffBlock).where(OneOffBlock.user_id == user.id)
    if ends_after is not None:
        query = query.where(OneOffBlock.end_at > ends_after)
    if starts_before is not None:
        query = query.where(OneOffBlock.start_at < starts_before)
    return list(db.scalars(query.order_by(OneOffBlock.start_at, OneOffBlock.id)))


def create_one_off_block(db: Session, user: User, data: OneOffBlockWrite) -> OneOffBlock:
    block = OneOffBlock(user_id=user.id, **data.model_dump())
    db.add(block)
    db.commit()
    return block


def update_one_off_block(
    db: Session, user: User, block_id: uuid.UUID, data: OneOffBlockWrite
) -> OneOffBlock:
    block = get_owned(db, OneOffBlock, block_id, user.id)
    for field, value in data.model_dump().items():
        setattr(block, field, value)
    db.commit()
    return block


def delete_one_off_block(db: Session, user: User, block_id: uuid.UUID) -> None:
    db.delete(get_owned(db, OneOffBlock, block_id, user.id))
    db.commit()


def get_preferences(db: Session, user: User) -> StudyPreferences:
    preferences = db.get(StudyPreferences, user.id)
    if preferences is None:
        raise InvalidFieldsError({"preferences": "Study preferences are missing."})
    return preferences


def update_preferences(db: Session, user: User, data: PreferencesWrite) -> StudyPreferences:
    preferences = get_preferences(db, user)
    for field, value in data.model_dump().items():
        setattr(preferences, field, value)
    db.commit()
    return preferences

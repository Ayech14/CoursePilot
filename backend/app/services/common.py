"""Helpers shared by domain services."""

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import User


def get_owned[M](db: Session, model: type[M], record_id: uuid.UUID, user_id: uuid.UUID) -> M:
    """Load a record belonging to this user.

    Every lookup by ID goes through here. A record owned by someone else gives the same error as
    one that does not exist, so IDs cannot be probed.
    """
    table: Any = model
    record = db.scalar(select(model).where(table.id == record_id, table.user_id == user_id))
    if record is None:
        raise NotFoundError
    return record


def mark_schedule_inputs_changed(db: Session, user_id: uuid.UUID) -> None:
    """Anything a plan depends on changed, so an open preview can no longer be trusted."""
    db.execute(
        update(User).where(User.id == user_id).values(schedule_version=User.schedule_version + 1)
    )

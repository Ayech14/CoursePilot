"""Helpers shared by domain services."""

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError


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

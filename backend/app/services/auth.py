"""Registration, login and refresh-token rotation."""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import Settings
from app.core.errors import EmailTakenError, InvalidCredentialsError, InvalidRefreshTokenError
from app.models import RefreshToken, StudyPreferences, User
from app.schemas.auth import RegisterRequest, UserUpdate
from app.services.common import mark_schedule_inputs_changed

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IssuedTokens:
    user: User
    access_token: str
    refresh_token: str


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _issue_tokens(
    db: Session, user: User, settings: Settings, family_id: uuid.UUID | None = None
) -> IssuedTokens:
    refresh_token = security.generate_refresh_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            family_id=family_id or uuid.uuid7(),
            token_hash=security.hash_refresh_token(refresh_token),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_days),
        )
    )
    access_token = security.create_access_token(
        user.id,
        settings.jwt_secret.get_secret_value(),
        timedelta(minutes=settings.access_token_minutes),
    )
    return IssuedTokens(user, access_token, refresh_token)


def register(db: Session, data: RegisterRequest, settings: Settings) -> IssuedTokens:
    user = User(
        email=_normalize_email(data.email),
        password_hash=security.hash_password(data.password),
        display_name=data.display_name,
        timezone=data.timezone,
    )
    db.add(user)
    try:
        # Relying on the unique index avoids the race in "check, then insert".
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise EmailTakenError from exc

    db.add(StudyPreferences(user_id=user.id))
    tokens = _issue_tokens(db, user, settings)
    db.commit()
    logger.info("user_registered", extra={"user_id": str(user.id)})
    return tokens


def login(db: Session, email: str, password: str, settings: Settings) -> IssuedTokens:
    user = db.scalar(select(User).where(User.email == _normalize_email(email)))
    if user is None:
        security.burn_password_check(password)
        raise InvalidCredentialsError
    if not security.verify_password(user.password_hash, password):
        raise InvalidCredentialsError

    if security.password_needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)

    # Keeps the table bounded without needing a scheduled cleanup job.
    db.execute(
        delete(RefreshToken).where(
            RefreshToken.user_id == user.id, RefreshToken.expires_at < datetime.now(UTC)
        )
    )
    tokens = _issue_tokens(db, user, settings)
    db.commit()
    return tokens


def refresh(db: Session, raw_token: str | None, settings: Settings) -> IssuedTokens:
    """Exchange a refresh token for a new one.

    A token can be exchanged only once. Seeing a used token again suggests it was stolen, so the
    whole login family is revoked, unless it happened within a few seconds of the original
    exchange, which is what two browser tabs refreshing at the same moment look like.
    """
    if raw_token is None:
        raise InvalidRefreshTokenError

    # The row lock serializes concurrent exchanges of the same token.
    stored = db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == security.hash_refresh_token(raw_token))
        .with_for_update()
    )
    now = datetime.now(UTC)
    if stored is None or stored.revoked_at is not None or stored.expires_at <= now:
        raise InvalidRefreshTokenError

    if stored.rotated_at is not None:
        age = now - stored.rotated_at
        if age > timedelta(seconds=settings.refresh_reuse_grace_seconds):
            _revoke_family(db, stored.family_id, now)
            db.commit()
            logger.warning("refresh_token_reuse", extra={"user_id": str(stored.user_id)})
            raise InvalidRefreshTokenError
    else:
        stored.rotated_at = now

    user = db.get_one(User, stored.user_id)
    tokens = _issue_tokens(db, user, settings, family_id=stored.family_id)
    db.commit()
    return tokens


def logout(db: Session, raw_token: str | None) -> None:
    """Revoke the login family. Unknown tokens are ignored, so logging out twice is safe."""
    if raw_token is None:
        return
    stored = db.scalar(
        select(RefreshToken).where(
            RefreshToken.token_hash == security.hash_refresh_token(raw_token)
        )
    )
    if stored is not None:
        _revoke_family(db, stored.family_id, datetime.now(UTC))
        db.commit()


def update_profile(db: Session, user: User, changes: UserUpdate) -> User:
    for field, value in changes.model_dump(exclude_unset=True, exclude_none=True).items():
        setattr(user, field, value)
    if changes.timezone is not None:
        mark_schedule_inputs_changed(db, user.id)
    db.commit()
    return user


def _revoke_family(db: Session, family_id: uuid.UUID, now: datetime) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=now)
    )

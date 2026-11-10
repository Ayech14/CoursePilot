"""Password hashing and token primitives. Contains no database or HTTP logic."""

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.errors import NotAuthenticatedError

_JWT_ALGORITHM = "HS256"
_ACCESS_TOKEN_TYPE = "access"  # noqa: S105  # A claim value, not a credential.

_hasher = PasswordHasher()  # Argon2id with the library's maintained default parameters.

# Verified when an email is unknown, so that response time does not reveal which emails exist.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerificationError, InvalidHashError:
        return False


def password_needs_rehash(password_hash: str) -> bool:
    return _hasher.check_needs_rehash(password_hash)


def burn_password_check(password: str) -> None:
    """Spend the same time as a real verification when no user was found."""
    verify_password(_DUMMY_HASH, password)


def create_access_token(user_id: uuid.UUID, secret: str, ttl: timedelta) -> str:
    now = datetime.now(UTC)
    claims = {"sub": str(user_id), "typ": _ACCESS_TOKEN_TYPE, "iat": now, "exp": now + ttl}
    return jwt.encode(claims, secret, algorithm=_JWT_ALGORITHM)


def decode_access_token(token: str, secret: str) -> uuid.UUID:
    """Return the user ID from a valid access token, or raise ``NotAuthenticatedError``."""
    try:
        # The algorithm list is fixed, which blocks algorithm-confusion attacks such as "none".
        claims = jwt.decode(
            token, secret, algorithms=[_JWT_ALGORITHM], options={"require": ["exp", "sub", "typ"]}
        )
        if claims["typ"] != _ACCESS_TOKEN_TYPE:
            raise NotAuthenticatedError
        return uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise NotAuthenticatedError from exc


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str) -> str:
    """Hash a refresh token for storage.

    A fast hash is appropriate here, unlike for passwords: the token is 384 bits of randomness,
    so there is nothing to brute-force. A leaked table of hashes cannot be replayed as tokens.
    """
    return hashlib.sha256(token.encode()).hexdigest()

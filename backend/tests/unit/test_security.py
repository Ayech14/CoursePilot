import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.core import security
from app.core.errors import NotAuthenticatedError

SECRET = "unit-test-secret-at-least-32-characters"
USER_ID = uuid.UUID("0190a000-0000-7000-8000-000000000001")


def test_password_hash_is_argon2id_and_verifies() -> None:
    hashed = security.hash_password("correct horse battery")
    assert hashed.startswith("$argon2id$")
    assert "correct horse" not in hashed
    assert security.verify_password(hashed, "correct horse battery")
    assert not security.verify_password(hashed, "wrong password")


def test_same_password_gets_different_hashes() -> None:
    assert security.hash_password("same password") != security.hash_password("same password")


def test_malformed_hash_is_a_failed_check_not_a_crash() -> None:
    assert not security.verify_password("not-a-hash", "anything")


def test_access_token_round_trip() -> None:
    token = security.create_access_token(USER_ID, SECRET, timedelta(minutes=5))
    assert security.decode_access_token(token, SECRET) == USER_ID


def test_expired_token_rejected() -> None:
    token = security.create_access_token(USER_ID, SECRET, timedelta(seconds=-1))
    with pytest.raises(NotAuthenticatedError):
        security.decode_access_token(token, SECRET)


def test_token_signed_with_other_secret_rejected() -> None:
    token = security.create_access_token(USER_ID, "x" * 40, timedelta(minutes=5))
    with pytest.raises(NotAuthenticatedError):
        security.decode_access_token(token, SECRET)


def test_unsigned_alg_none_token_rejected() -> None:
    token = jwt.encode(
        {
            "sub": str(USER_ID),
            "typ": "access",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        key="",
        algorithm="none",
    )
    with pytest.raises(NotAuthenticatedError):
        security.decode_access_token(token, SECRET)


def test_token_of_wrong_type_rejected() -> None:
    token = jwt.encode(
        {
            "sub": str(USER_ID),
            "typ": "something-else",
            "exp": datetime.now(UTC) + timedelta(minutes=5),
        },
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(NotAuthenticatedError):
        security.decode_access_token(token, SECRET)


def test_token_with_invalid_subject_rejected() -> None:
    token = jwt.encode(
        {"sub": "not-a-uuid", "typ": "access", "exp": datetime.now(UTC) + timedelta(minutes=5)},
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(NotAuthenticatedError):
        security.decode_access_token(token, SECRET)


def test_refresh_tokens_are_unique_and_hash_is_stable() -> None:
    first, second = security.generate_refresh_token(), security.generate_refresh_token()
    assert first != second
    assert security.hash_refresh_token(first) == security.hash_refresh_token(first)
    assert security.hash_refresh_token(first) != first

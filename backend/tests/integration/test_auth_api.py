import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx2
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.v1.auth import REFRESH_COOKIE
from app.core.config import get_settings
from app.core.security import create_access_token, hash_refresh_token
from app.models import RefreshToken, StudyPreferences, User

PASSWORD = "a-long-enough-password"


def registration(email: str = "ada@example.com", **overrides: Any) -> dict[str, Any]:
    return {
        "email": email,
        "password": PASSWORD,
        "display_name": "Ada",
        "timezone": "America/Toronto",
    } | overrides


def register(client: TestClient, email: str = "ada@example.com") -> dict[str, Any]:
    response = client.post("/api/v1/auth/register", json=registration(email))
    assert response.status_code == 201
    return response.json()


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def refresh_cookie(client: TestClient) -> str:
    return client.cookies.get(REFRESH_COOKIE, path="/api/v1/auth")


def post_refresh(client: TestClient, token: str) -> httpx2.Response:
    """Present a specific refresh token, as the browser holding it would."""
    client.cookies.clear()
    client.cookies.set(REFRESH_COOKIE, token, domain="testserver.local", path="/api/v1/auth")
    return client.post("/api/v1/auth/refresh")


# --- Registration ---------------------------------------------------------------------------


def test_register_creates_user_and_default_preferences(client: TestClient, db: Session) -> None:
    body = register(client)
    assert body["user"]["email"] == "ada@example.com"
    assert body["user"]["timezone"] == "America/Toronto"
    assert body["access_token"]

    user = db.scalar(select(User).where(User.email == "ada@example.com"))
    assert user is not None
    assert user.password_hash.startswith("$argon2id$")
    assert db.get(StudyPreferences, user.id) is not None


def test_response_never_exposes_the_password_hash(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json=registration())
    assert "password" not in response.text
    assert "argon2" not in response.text


def test_refresh_cookie_is_hardened(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json=registration())
    cookie = response.headers["set-cookie"].lower()
    assert "httponly" in cookie
    assert "samesite=strict" in cookie
    assert "path=/api/v1/auth" in cookie


def test_refresh_token_is_stored_only_as_a_hash(client: TestClient, db: Session) -> None:
    register(client)
    raw = refresh_cookie(client)
    stored = db.scalars(select(RefreshToken)).one()
    assert stored.token_hash == hash_refresh_token(raw)
    assert stored.token_hash != raw


def test_duplicate_email_ignores_case(client: TestClient) -> None:
    register(client)
    response = client.post("/api/v1/auth/register", json=registration("ADA@Example.COM"))
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "email_taken"


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"password": "short"}, "password"),
        ({"email": "not-an-email"}, "email"),
        ({"timezone": "Mars/Base"}, "timezone"),
        ({"display_name": "   "}, "display_name"),
    ],
)
def test_invalid_registration_rejected(
    client: TestClient, overrides: dict[str, str], field: str
) -> None:
    response = client.post("/api/v1/auth/register", json=registration(**overrides))
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert [item["field"] for item in error["details"]] == [field]


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"password": "short"}, "Must be at least 10 characters."),
        ({"display_name": ""}, "This field is required."),
        ({"timezone": "Mars/Base"}, "must be an IANA time zone name, such as America/Toronto"),
        ({"email": "nope"}, "An email address must have an @-sign."),
    ],
)
def test_validation_messages_are_readable(
    client: TestClient, overrides: dict[str, str], expected: str
) -> None:
    response = client.post("/api/v1/auth/register", json=registration(**overrides))
    assert response.json()["error"]["details"][0]["message"] == expected


def test_validation_errors_do_not_echo_the_password(client: TestClient) -> None:
    response = client.post("/api/v1/auth/register", json=registration(password="sekret12"))
    assert response.status_code == 422
    assert "sekret12" not in response.text


# --- Login ----------------------------------------------------------------------------------


def test_login_succeeds_and_ignores_email_case(client: TestClient) -> None:
    register(client)
    response = client.post(
        "/api/v1/auth/login", json={"email": "ADA@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200
    token = response.json()["access_token"]
    assert client.get("/api/v1/users/me", headers=bearer(token)).status_code == 200


def test_wrong_password_and_unknown_email_look_identical(client: TestClient) -> None:
    register(client)
    wrong = client.post(
        "/api/v1/auth/login", json={"email": "ada@example.com", "password": "wrong-password"}
    )
    unknown = client.post(
        "/api/v1/auth/login", json={"email": "nobody@example.com", "password": PASSWORD}
    )
    assert wrong.status_code == unknown.status_code == 401
    first, second = wrong.json()["error"], unknown.json()["error"]
    assert (first["code"], first["message"]) == (second["code"], second["message"])


def test_login_removes_expired_tokens(client: TestClient, db: Session) -> None:
    body = register(client)
    expired = db.scalars(select(RefreshToken)).one()
    expired.expires_at = datetime.now(UTC) - timedelta(days=1)
    db.flush()

    client.post("/api/v1/auth/login", json={"email": "ada@example.com", "password": PASSWORD})

    db.expire_all()
    remaining = db.scalars(select(RefreshToken)).all()
    assert len(remaining) == 1
    assert str(remaining[0].user_id) == body["user"]["id"]
    assert remaining[0].expires_at > datetime.now(UTC)


# --- Access control -------------------------------------------------------------------------


def test_me_requires_a_token(client: TestClient) -> None:
    response = client.get("/api/v1/users/me")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"
    assert response.headers["www-authenticate"] == "Bearer"


def test_garbage_token_rejected(client: TestClient) -> None:
    assert client.get("/api/v1/users/me", headers=bearer("garbage")).status_code == 401


def test_expired_token_rejected(client: TestClient) -> None:
    user_id = register(client)["user"]["id"]
    token = create_access_token(
        uuid.UUID(user_id),
        get_settings().jwt_secret.get_secret_value(),
        timedelta(seconds=-1),
    )
    assert client.get("/api/v1/users/me", headers=bearer(token)).status_code == 401


def test_token_of_deleted_user_rejected(client: TestClient, db: Session) -> None:
    token = register(client)["access_token"]
    db.delete(db.scalars(select(User)).one())
    db.flush()
    assert client.get("/api/v1/users/me", headers=bearer(token)).status_code == 401


def test_each_token_sees_only_its_own_user(client: TestClient) -> None:
    ada, grace = register(client, "ada@example.com"), register(client, "grace@example.com")
    assert (
        client.get("/api/v1/users/me", headers=bearer(ada["access_token"])).json()["email"]
        == "ada@example.com"
    )
    assert (
        client.get("/api/v1/users/me", headers=bearer(grace["access_token"])).json()["email"]
        == "grace@example.com"
    )


def test_profile_update_affects_only_the_caller(client: TestClient) -> None:
    ada, grace = register(client, "ada@example.com"), register(client, "grace@example.com")
    response = client.patch(
        "/api/v1/users/me",
        headers=bearer(ada["access_token"]),
        json={"timezone": "Europe/Paris", "display_name": "Ada L."},
    )
    assert response.status_code == 200
    assert response.json()["timezone"] == "Europe/Paris"
    unchanged = client.get("/api/v1/users/me", headers=bearer(grace["access_token"])).json()
    assert unchanged["timezone"] == "America/Toronto"


def test_profile_update_cannot_change_email_or_id(client: TestClient) -> None:
    ada = register(client)
    response = client.patch(
        "/api/v1/users/me",
        headers=bearer(ada["access_token"]),
        json={"email": "evil@example.com", "id": "x", "password_hash": "y"},
    )
    assert response.status_code == 200
    assert response.json()["email"] == "ada@example.com"


def test_profile_rejects_invalid_time_zone(client: TestClient) -> None:
    ada = register(client)
    response = client.patch(
        "/api/v1/users/me", headers=bearer(ada["access_token"]), json={"timezone": "Nowhere"}
    )
    assert response.status_code == 422


# --- Refresh rotation -----------------------------------------------------------------------


def test_refresh_issues_new_working_tokens(client: TestClient) -> None:
    register(client)
    original = refresh_cookie(client)

    response = post_refresh(client, original)

    assert response.status_code == 200
    assert refresh_cookie(client) != original
    token = response.json()["access_token"]
    assert client.get("/api/v1/users/me", headers=bearer(token)).status_code == 200


def test_refresh_without_cookie_rejected(client: TestClient) -> None:
    response = client.post("/api/v1/auth/refresh")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_refresh_token"


def test_unknown_refresh_token_rejected(client: TestClient) -> None:
    assert post_refresh(client, "made-up-token").status_code == 401


def test_expired_refresh_token_rejected(client: TestClient, db: Session) -> None:
    register(client)
    original = refresh_cookie(client)
    db.scalars(select(RefreshToken)).one().expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db.flush()
    assert post_refresh(client, original).status_code == 401


def test_reused_token_within_grace_window_is_tolerated(client: TestClient) -> None:
    register(client)
    original = refresh_cookie(client)
    assert post_refresh(client, original).status_code == 200
    assert post_refresh(client, original).status_code == 200


def test_reused_token_after_grace_window_revokes_the_family(
    client: TestClient, db: Session
) -> None:
    register(client)
    stolen = refresh_cookie(client)
    assert post_refresh(client, stolen).status_code == 200
    legitimate = refresh_cookie(client)

    stored = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(stolen))
    )
    assert stored is not None
    stored.rotated_at = datetime.now(UTC) - timedelta(minutes=5)
    db.flush()

    assert post_refresh(client, stolen).status_code == 401
    assert post_refresh(client, legitimate).status_code == 401


def test_reuse_does_not_revoke_other_logins(client: TestClient, db: Session) -> None:
    register(client)
    stolen = refresh_cookie(client)
    client.post("/api/v1/auth/login", json={"email": "ada@example.com", "password": PASSWORD})
    other_device = refresh_cookie(client)

    assert post_refresh(client, stolen).status_code == 200
    stored = db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == hash_refresh_token(stolen))
    )
    assert stored is not None
    stored.rotated_at = datetime.now(UTC) - timedelta(minutes=5)
    db.flush()
    assert post_refresh(client, stolen).status_code == 401

    assert post_refresh(client, other_device).status_code == 200


# --- Logout ---------------------------------------------------------------------------------


def test_logout_revokes_the_refresh_token(client: TestClient) -> None:
    register(client)
    original = refresh_cookie(client)

    response = client.post("/api/v1/auth/logout")

    assert response.status_code == 204
    assert client.cookies.get(REFRESH_COOKIE, path="/api/v1/auth") is None
    assert post_refresh(client, original).status_code == 401


def test_logout_is_idempotent(client: TestClient) -> None:
    assert client.post("/api/v1/auth/logout").status_code == 204
    assert client.post("/api/v1/auth/logout").status_code == 204

"""Sign-in and registration limits, through the real endpoints."""

import uuid

from fastapi.testclient import TestClient

from tests.integration.helpers import API

PASSWORD = "a-long-enough-password"


def register(client: TestClient, email: str | None = None) -> tuple[int, str]:
    email = email or f"{uuid.uuid4().hex}@example.com"
    response = client.post(
        f"{API}/auth/register",
        json={"email": email, "password": PASSWORD, "display_name": "S", "timezone": "UTC"},
    )
    return response.status_code, email


def login(client: TestClient, email: str, password: str) -> int:
    return client.post(f"{API}/auth/login", json={"email": email, "password": password}).status_code


def test_five_wrong_passwords_lock_that_account_for_a_while(client: TestClient) -> None:
    _, email = register(client)
    assert [login(client, email, "wrong-password") for _ in range(5)] == [401] * 5

    response = client.post(f"{API}/auth/login", json={"email": email, "password": PASSWORD})
    # Even the right password waits, or guessing could continue by spotting the one success.
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert int(response.headers["Retry-After"]) > 0


def test_the_lock_is_per_email_ignoring_case(client: TestClient) -> None:
    _, locked = register(client)
    _, other = register(client)
    for _ in range(5):
        login(client, locked.upper(), "wrong-password")
    assert login(client, locked, PASSWORD) == 429
    assert login(client, other, PASSWORD) == 200


def test_a_successful_sign_in_resets_the_count(client: TestClient) -> None:
    _, email = register(client)
    for _ in range(4):
        login(client, email, "wrong-password")
    assert login(client, email, PASSWORD) == 200
    assert [login(client, email, "wrong-password") for _ in range(4)] == [401] * 4
    assert login(client, email, PASSWORD) == 200


def test_trying_many_emails_from_one_address_is_also_limited(client: TestClient) -> None:
    for _ in range(20):
        login(client, f"{uuid.uuid4().hex}@example.com", "guess")
    _, email = register(client)
    assert login(client, email, PASSWORD) == 429


def test_registration_is_limited_per_address(client: TestClient) -> None:
    assert [register(client)[0] for _ in range(10)] == [201] * 10
    status, _ = register(client)
    assert status == 429

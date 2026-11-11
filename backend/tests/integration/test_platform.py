"""Health checks, the error format and request correlation."""

import json
import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.main import create_app


def test_liveness(client: TestClient) -> None:
    assert client.get("/health").json() == {"status": "ok"}


def test_readiness_checks_the_database(client: TestClient) -> None:
    assert client.get("/health/ready").json() == {"status": "ready"}


def test_openapi_documents_auth_routes(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/auth/login" in paths
    assert "/api/v1/users/me" in paths


def test_unknown_route_uses_standard_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/nope")
    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "not_found"
    assert error["request_id"] == response.headers["x-request-id"]


def test_wrong_method_uses_standard_error_shape(client: TestClient) -> None:
    response = client.get("/api/v1/auth/login")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_safe_request_id_is_preserved(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "client-supplied-id-1"})
    assert response.headers["x-request-id"] == "client-supplied-id-1"


def test_unsafe_request_id_is_replaced(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": 'bad" id\t{}'})
    assert response.headers["x-request-id"] != 'bad" id\t{}'


def log_lines(capsys: pytest.CaptureFixture[str]) -> list[dict[str, Any]]:
    """Read the JSON lines the application actually wrote to stdout."""
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]


def test_unhandled_exception_is_generic_and_logged(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    app = create_app()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("secret internal detail")

    client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="coursepilot.access"):
        response = client.get("/boom")

    assert response.status_code == 500
    assert "secret internal detail" not in response.text
    error = response.json()["error"]
    assert error["code"] == "internal_error"
    assert error["request_id"] == response.headers["x-request-id"]

    entry = next(e for e in log_lines(capsys) if e["message"] == "unhandled_exception")
    assert "secret internal detail" in entry["exception"]
    assert entry["request_id"] == error["request_id"]


def test_access_log_omits_query_string(
    caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    client = TestClient(create_app())
    with caplog.at_level(logging.INFO, logger="coursepilot.access"):
        client.get("/health?token=private-value")

    entry = next(e for e in log_lines(capsys) if e["message"] == "request")
    assert entry["path"] == "/health"
    assert entry["status"] == 200
    assert "private-value" not in json.dumps(entry)


def test_database_race_returns_a_clean_conflict() -> None:
    app = create_app()

    @app.get("/race")
    def race() -> None:
        raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    response = TestClient(app, raise_server_exceptions=False).get("/race")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert "duplicate key" not in response.text


SECURITY_HEADERS = {
    "x-content-type-options": "nosniff",
    "referrer-policy": "no-referrer",
    "x-frame-options": "DENY",
    "content-security-policy": "default-src 'none'; frame-ancestors 'none'",
}


def test_api_answers_carry_security_headers_and_are_never_cached(client: TestClient) -> None:
    for response in (client.get("/api/v1/users/me"), client.get("/api/v1/nowhere")):
        for name, value in SECURITY_HEADERS.items():
            assert response.headers[name] == value, name
        assert response.headers["cache-control"] == "no-store"
    # Plain HTTP in development: telling browsers to insist on HTTPS would lock them out.
    assert "strict-transport-security" not in client.get("/health").headers


def test_even_an_unhandled_error_carries_them() -> None:
    app = create_app()

    @app.get("/api/v1/boom")
    def boom() -> None:
        raise RuntimeError("boom")

    response = TestClient(app, raise_server_exceptions=False).get("/api/v1/boom")
    assert response.status_code == 500
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"


def test_the_api_docs_keep_working(client: TestClient) -> None:
    response = client.get("/docs")
    assert response.status_code == 200
    assert "content-security-policy" not in response.headers


def test_production_tells_browsers_to_use_https_only(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.core.config import get_settings

    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("JWT_SECRET", "a-production-secret-that-is-long-enough")
    monkeypatch.setenv("CALENDAR_LINK_KEY", "another-production-secret-long-enough")
    monkeypatch.setenv("COOKIE_SECURE", "true")
    get_settings.cache_clear()
    try:
        response = TestClient(create_app()).get("/health")
    finally:
        get_settings.cache_clear()
    assert response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"

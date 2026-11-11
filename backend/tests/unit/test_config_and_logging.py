import json
import logging
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.logging import JsonFormatter, request_id_var
from app.schemas.auth import UserUpdate

GOOD_SECRET = "a-real-secret-value-that-is-long-enough-to-pass"
LINK_KEY = "a-separate-key-for-calendar-links-long-enough"


def make_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "_env_file": None,
        "database_url": "postgresql+psycopg://u:p@h/d",
        "jwt_secret": GOOD_SECRET,
        "environment": "production",
        "cookie_secure": True,
        "calendar_link_key": LINK_KEY,
    }
    return Settings(**(values | overrides))


def test_valid_production_settings_accepted() -> None:
    assert make_settings().environment == "production"


def test_production_refuses_development_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        make_settings(jwt_secret="dev-only-secret-not-for-any-real-deployment")


def test_production_requires_secure_cookies() -> None:
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        make_settings(cookie_secure=False)


def test_short_secret_refused_everywhere() -> None:
    with pytest.raises(ValidationError):
        make_settings(environment="local", jwt_secret="short")


def test_secret_not_shown_in_repr() -> None:
    shown = repr(make_settings())
    assert GOOD_SECRET not in shown
    assert LINK_KEY not in shown


def test_log_lines_are_json_with_request_id_and_extras() -> None:
    record = logging.LogRecord("test", logging.INFO, __file__, 1, "hello %s", ("world",), None)
    record.duration_ms = 12.5
    token = request_id_var.set("abc123")
    try:
        line = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert line["message"] == "hello world"
    assert line["level"] == "INFO"
    assert line["request_id"] == "abc123"
    assert line["duration_ms"] == 12.5


@pytest.mark.parametrize("zone", ["America/Toronto", "Asia/Tehran", "UTC", "Asia/Kolkata"])
def test_valid_time_zones_accepted(zone: str) -> None:
    assert UserUpdate(timezone=zone).timezone == zone


@pytest.mark.parametrize("zone", ["Mars/Base", "EST5", "", "../etc/passwd", "localtime"])
def test_invalid_time_zones_rejected(zone: str) -> None:
    with pytest.raises(ValidationError):
        UserUpdate(timezone=zone)

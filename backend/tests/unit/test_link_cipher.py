"""Encryption of calendar links, and the production rule that it has its own key."""

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.link_cipher import LinkCipher

LINK = "https://eclass.yorku.ca/calendar/export_execute.php?userid=7&authtoken=SECRET123"


def test_round_trips_without_showing_the_link() -> None:
    cipher = LinkCipher(b"k" * 32)
    token = cipher.encrypt(LINK)
    assert "SECRET123" not in token and "eclass" not in token
    assert cipher.decrypt(token) == LINK


def test_encrypting_twice_gives_different_text_but_the_same_digest() -> None:
    cipher = LinkCipher(b"k" * 32)
    assert cipher.encrypt(LINK) != cipher.encrypt(LINK)
    assert cipher.digest(LINK) == cipher.digest(LINK)
    assert cipher.digest(LINK) != cipher.digest(LINK + "x")


def test_another_key_can_neither_read_it_nor_match_its_digest() -> None:
    ours, theirs = LinkCipher(b"k" * 32), LinkCipher(b"j" * 32)
    with pytest.raises(ValueError, match="CALENDAR_LINK_KEY"):
        theirs.decrypt(ours.encrypt(LINK))
    assert ours.digest(LINK) != theirs.digest(LINK)


def production(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "environment": "production",
        "database_url": "postgresql+psycopg://x/y",
        "jwt_secret": "a-production-secret-that-is-long-enough",
        "cookie_secure": True,
        "calendar_link_key": "another-production-secret-long-enough",
    } | overrides
    return Settings(**values)  # type: ignore[arg-type]


def test_production_requires_its_own_link_key() -> None:
    production()
    with pytest.raises(ValidationError, match="CALENDAR_LINK_KEY must be set"):
        production(calendar_link_key=None)
    with pytest.raises(ValidationError, match="must differ from JWT_SECRET"):
        production(calendar_link_key="a-production-secret-that-is-long-enough")

"""The migration that encrypts calendar links keeps every existing link, both ways.

It runs on its own scratch database, so the shared test database is never downgraded.
"""

import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.core.link_cipher import LinkCipher, master_key
from tests.conftest import TEST_DATABASE_URL, alembic_config

BEFORE, AFTER = "d7f3b8a2c614", "e2a9c5f1d837"
LINK = "https://eclass.yorku.ca/calendar/export_execute.php?authtoken=SECRET123"


@pytest.fixture
def scratch_url(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    url = make_url(TEST_DATABASE_URL)
    name = f"{url.database}_migration"
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    scratch = url.set(database=name).render_as_string(hide_password=False)
    monkeypatch.setenv("DATABASE_URL", scratch)
    get_settings.cache_clear()
    yield scratch
    get_settings.cache_clear()
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
    admin.dispose()


def test_existing_links_are_encrypted_and_restored_on_downgrade(scratch_url: str) -> None:
    config = alembic_config()
    command.upgrade(config, BEFORE)
    engine = create_engine(scratch_url)
    user, feed = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as db:
        db.execute(
            text(
                "INSERT INTO users (id, email, password_hash, display_name, timezone) "
                "VALUES (:id, 'a@example.com', 'x', 'A', 'UTC')"
            ),
            {"id": user},
        )
        db.execute(
            text(
                "INSERT INTO calendar_feeds (id, user_id, name, url) "
                "VALUES (:id, :u, 'eClass', :url)"
            ),
            {"id": feed, "u": user, "url": LINK},
        )

    command.upgrade(config, AFTER)
    with engine.connect() as db:
        row = db.execute(
            text("SELECT url_ciphertext, url_digest, url_host FROM calendar_feeds")
        ).one()
        columns = {
            c
            for (c,) in db.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'calendar_feeds'"
                )
            )
        }
    cipher = LinkCipher(master_key(get_settings()))
    assert "url" not in columns
    assert "SECRET123" not in row.url_ciphertext
    assert cipher.decrypt(row.url_ciphertext) == LINK
    assert row.url_digest == cipher.digest(LINK)
    assert row.url_host == "eclass.yorku.ca"

    command.downgrade(config, BEFORE)
    with engine.connect() as db:
        assert db.execute(text("SELECT url FROM calendar_feeds")).scalar_one() == LINK
    engine.dispose()

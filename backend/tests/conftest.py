"""Shared fixtures.

Integration tests use a real PostgreSQL database because the guarantees being tested, such as
exclusion constraints and partial indexes, do not exist in SQLite. The schema is built by the
actual migrations, so the migrations are exercised on every run.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://coursepilot:coursepilot@localhost:5433/coursepilot_test",
)

# Must be set before anything imports the application settings.
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ["JWT_SECRET"] = "test-secret-that-is-at-least-32-characters-long"
os.environ["COOKIE_SECURE"] = "false"
os.environ["CORS_ORIGINS"] = "[]"
# INFO, so that every log statement actually runs. A bad one can crash a request.
os.environ["LOG_LEVEL"] = "INFO"

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db.session import get_db  # noqa: E402
from app.main import create_app  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parent.parent


def alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return config


def _recreate_test_database() -> None:
    url = make_url(TEST_DATABASE_URL)
    assert url.database is not None
    if not url.database.endswith("_test"):
        pytest.exit(f"Refusing to recreate a non-test database: {url.database}", returncode=1)

    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{url.database}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    _recreate_test_database()
    config = alembic_config()
    # Upgrading, downgrading and upgrading again proves that migrations are reversible.
    command.upgrade(config, "head")
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    test_engine = create_engine(TEST_DATABASE_URL)
    yield test_engine
    test_engine.dispose()


@pytest.fixture
def connection(engine: Engine) -> Iterator[Connection]:
    with engine.connect() as conn:
        outer = conn.begin()
        yield conn
        outer.rollback()


@pytest.fixture
def db(connection: Connection) -> Iterator[Session]:
    """A session whose commits become savepoints, so each test is rolled back in full."""
    with Session(
        bind=connection, join_transaction_mode="create_savepoint", expire_on_commit=False
    ) as session:
        yield session


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app) as test_client:
        yield test_client

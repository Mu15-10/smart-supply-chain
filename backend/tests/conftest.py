"""Shared test bootstrap for SQLite-local and PostgreSQL CI runs."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import redis
from alembic.config import Config
from sqlalchemy import text

from alembic import command

BACKEND_DIR = Path(__file__).resolve().parents[1]
ALEMBIC_CONFIG = BACKEND_DIR / "alembic.ini"
USING_EXTERNAL_DATABASE = bool(os.environ.get("TEST_DATABASE_URL"))
LOCAL_DATABASE_PATH = BACKEND_DIR / ".pytest.sqlite3"
if not USING_EXTERNAL_DATABASE:
    LOCAL_DATABASE_PATH.unlink(missing_ok=True)
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{LOCAL_DATABASE_PATH}"
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("SERVICE", "all")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("JWT_SECRET", "CHANGE_ME_TEST_JWT_SECRET_12345678901234567890")


def _alembic_config(url: str) -> Config:
    config = Config(str(ALEMBIC_CONFIG))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    config.attributes["database_url"] = url
    return config


def pytest_report_header() -> str:
    scheme = urlsplit(TEST_DATABASE_URL).scheme
    dialect = scheme.split("+", 1)[0] or "unknown"
    return f"test database dialect: {dialect} (TEST_DATABASE_URL={'set' if USING_EXTERNAL_DATABASE else 'unset'})"


def pytest_sessionstart(session: pytest.Session) -> None:
    scheme = urlsplit(TEST_DATABASE_URL).scheme
    dialect = scheme.split("+", 1)[0] or "unknown"
    print(f"[test-bootstrap] database dialect: {dialect}")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line("markers", "postgres: test requires PostgreSQL via TEST_DATABASE_URL")


@pytest.fixture(scope="session", autouse=True)
def migrated_database():
    """Build the test schema only through Alembic, never SQLAlchemy create_all."""
    command.upgrade(_alembic_config(TEST_DATABASE_URL), "head")
    yield


@pytest.fixture(autouse=True)
def isolate_database_and_redis(migrated_database):
    """Keep tests independent while preserving Alembic's version table."""
    from app.main import Base, engine, rds

    table_names = [table.name for table in Base.metadata.sorted_tables]
    with engine.begin() as connection:
        if engine.dialect.name == "postgresql":
            names = ", ".join(f'"{name}"' for name in table_names)
            if names:
                # Names come exclusively from trusted SQLAlchemy metadata, not user input.
                connection.execute(text(f"TRUNCATE TABLE {names} RESTART IDENTITY CASCADE"))  # noqa: S608
        else:
            for name in reversed(table_names):
                connection.execute(text(f'DELETE FROM "{name}"'))

    if rds is not None:
        try:
            rds.flushdb()
        except redis.exceptions.RedisError as exc:
            # The application remains fail-closed in production; local tests can run without Redis.
            logging.getLogger(__name__).debug("Redis test cleanup skipped: %s", exc)
    yield


@pytest.fixture(scope="session", autouse=True)
def migration_cleanup():
    yield
    # The test database is disposable in CI; do not downgrade the shared application schema here.

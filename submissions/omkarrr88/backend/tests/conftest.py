"""Shared fixtures.

Unit tests (tests/unit) need nothing external. Integration tests (tests/integration) run against a
real Postgres with pgvector, set by TEST_DATABASE_URL; the schema is created by the real Alembic
migration and every table is emptied after each test.
"""

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.base import Base
from app.db.session import make_session_factory
from app.main import create_app

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://documind:documind@localhost:5433/documind_test"
)


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    for item in items:
        kind = "integration" if "integration" in item.path.parts else "unit"
        item.add_marker(getattr(pytest.mark, kind))


def make_test_settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "app_env": "test",
        "database_url": TEST_DATABASE_URL,
        "llm_provider": "fake",
        "embedding_provider": "fake",
        "log_level": "WARNING",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def _create_database_if_missing(url: str) -> None:
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def settings() -> Settings:
    return make_test_settings()


@pytest.fixture(scope="session")
def migrated_database(settings: Settings) -> str:
    _create_database_if_missing(settings.database_url)
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["database_url"] = settings.database_url
    command.upgrade(config, "head")
    return settings.database_url


@pytest.fixture(scope="session")
def session_factory(settings: Settings, migrated_database: str) -> Iterator[sessionmaker[Session]]:
    factory = make_session_factory(settings)
    yield factory
    factory.kw["bind"].dispose()


@pytest.fixture
def db(session_factory: sessionmaker[Session]) -> Iterator[sessionmaker[Session]]:
    """A session factory for one test; all tables are emptied afterwards."""
    yield session_factory
    tables = ", ".join(table.name for table in Base.metadata.sorted_tables)
    with session_factory.begin() as session:
        session.execute(text(f"TRUNCATE {tables} CASCADE"))


@pytest.fixture
def client(settings: Settings, db: sessionmaker[Session]) -> Iterator[TestClient]:
    app = create_app(settings)
    app.state.session_factory = db
    with TestClient(app) as test_client:
        yield test_client

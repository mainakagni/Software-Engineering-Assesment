"""Shared fixtures.

Unit tests (tests/unit) need nothing external. Integration tests (tests/integration) run against a
real Postgres with pgvector, set by TEST_DATABASE_URL.
"""

import os
from typing import Any

import pytest

from app.config import Settings

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

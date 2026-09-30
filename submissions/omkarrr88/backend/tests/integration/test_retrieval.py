"""Index search settings that depend on the installed pgvector version."""

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from app.config import VECTOR_DIM
from app.qa import retrieval
from app.qa.retrieval import search_chunks, supports_iterative_scan


@pytest.mark.parametrize(
    ("version", "setting", "value"),
    [("0.8.1", "hnsw.iterative_scan", "relaxed_order"), ("0.7.4", "hnsw.ef_search", "1000")],
)
def test_the_search_is_widened_for_the_installed_version(
    db: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    version: str,
    setting: str,
    value: str,
) -> None:
    monkeypatch.setattr(retrieval, "_pgvector_version", lambda session: version)
    with db() as session:
        assert search_chunks(session, uuid.uuid4(), [0.1] * VECTOR_DIM, k=3) == []
        assert session.execute(text(f"SHOW {setting}")).scalar() == value


def test_the_real_version_is_read_from_the_catalog(db: sessionmaker[Session]) -> None:
    with db() as session:
        version = retrieval._pgvector_version(session)
    assert version is not None
    assert supports_iterative_scan(version)  # the test database runs pgvector 0.8

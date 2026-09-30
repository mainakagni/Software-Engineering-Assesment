"""The migration creates what the application relies on."""

import uuid

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import func, insert, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Chunk, Document, DocumentBlob, IngestionJob, User
from tests.conftest import BACKEND_DIR

ZERO_VECTOR = [0.0] * 768


def _user(session: Session) -> uuid.UUID:
    user_id = uuid.uuid4()
    session.execute(insert(User).values(id=user_id, email=f"{user_id}@x.test", password_hash="h"))
    return user_id


def _document(session: Session, owner_id: uuid.UUID) -> uuid.UUID:
    document_id = uuid.uuid4()
    session.execute(
        insert(Document).values(
            id=document_id,
            owner_id=owner_id,
            filename="a.txt",
            content_type="text/plain",
            size_bytes=1,
            sha256=uuid.uuid4().hex * 2,
        )
    )
    return document_id


def _chunk(document_id: uuid.UUID, owner_id: uuid.UUID) -> dict[str, object]:
    return {
        "document_id": document_id,
        "owner_id": owner_id,
        "chunk_index": 0,
        "text": "hello",
        "char_count": 5,
        "embedding": ZERO_VECTOR,
    }


def test_models_and_migration_agree(migrated_database: str) -> None:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["database_url"] = migrated_database
    command.check(config)  # raises if autogenerate would produce a new migration


def test_hnsw_index_exists(db: sessionmaker[Session]) -> None:
    with db() as session:
        definition: str = session.execute(
            text("SELECT indexdef FROM pg_indexes WHERE indexname = 'ix_chunks_embedding_hnsw'")
        ).scalar_one()
    assert "hnsw" in definition
    assert "vector_cosine_ops" in definition


def test_chunk_owner_must_match_its_document_owner(db: sessionmaker[Session]) -> None:
    with db.begin() as session:
        alice, mallory = _user(session), _user(session)
        document_id = _document(session, alice)
    with pytest.raises(IntegrityError), db.begin() as session:
        session.execute(insert(Chunk).values(**_chunk(document_id, mallory)))


def test_deleting_a_document_removes_blob_jobs_and_chunks(db: sessionmaker[Session]) -> None:
    with db.begin() as session:
        owner = _user(session)
        document_id = _document(session, owner)
        session.execute(insert(DocumentBlob).values(document_id=document_id, data=b"x"))
        session.execute(insert(IngestionJob).values(document_id=document_id))
        session.execute(insert(Chunk).values(**_chunk(document_id, owner)))

    with db.begin() as session:
        session.execute(text("DELETE FROM documents WHERE id = :id"), {"id": document_id})

    with db() as session:
        for model in (DocumentBlob, IngestionJob, Chunk):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_emails_must_be_stored_lower_case(db: sessionmaker[Session]) -> None:
    with pytest.raises(IntegrityError), db.begin() as session:
        session.execute(insert(User).values(email="Alice@Example.com", password_hash="h"))


def test_document_status_is_constrained(db: sessionmaker[Session]) -> None:
    with db.begin() as session:
        document_id = _document(session, _user(session))
    with pytest.raises(IntegrityError), db.begin() as session:
        session.execute(
            text("UPDATE documents SET status = 'done' WHERE id = :id"), {"id": document_id}
        )

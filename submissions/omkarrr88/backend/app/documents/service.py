"""Document records. Every query is scoped to the owner, and someone else's document is a 404."""

import logging
import uuid

from sqlalchemy import delete, func, insert, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentBlob, IngestionJob, User
from app.documents.validation import ValidatedUpload
from app.errors import ConflictError, NotFoundError

logger = logging.getLogger(__name__)

NOT_FOUND_MESSAGE = "Document not found."


def create_document(
    session: Session,
    owner_id: uuid.UUID,
    upload: ValidatedUpload,
    *,
    max_documents: int,
    request_id: str | None,
) -> Document:
    """Stores the document, its bytes and its ingestion job in one transaction."""
    # Lock the owner's row so two parallel uploads cannot both pass the document limit.
    session.execute(select(User.id).where(User.id == owner_id).with_for_update())
    count = session.scalar(select(func.count()).where(Document.owner_id == owner_id)) or 0
    if count >= max_documents:
        raise ConflictError(
            f"You have reached the limit of {max_documents} documents. Delete one to add another."
        )
    if session.scalar(
        select(Document.id).where(Document.owner_id == owner_id, Document.sha256 == upload.sha256)
    ):
        raise ConflictError("You have already uploaded this file.")

    document = Document(
        owner_id=owner_id,
        filename=upload.filename,
        content_type=upload.content_type,
        size_bytes=len(upload.data),
        sha256=upload.sha256,
        status="queued",
    )
    session.add(document)
    session.flush()
    session.execute(insert(DocumentBlob).values(document_id=document.id, data=upload.data))
    session.execute(insert(IngestionJob).values(document_id=document.id, request_id=request_id))
    try:
        session.commit()
    except IntegrityError as exc:  # the same file uploaded twice at the same moment
        session.rollback()
        raise ConflictError("You have already uploaded this file.") from exc
    return document


def list_documents(
    session: Session, owner_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[Document], int]:
    total = session.scalar(select(func.count()).where(Document.owner_id == owner_id)) or 0
    documents = session.scalars(
        select(Document)
        .where(Document.owner_id == owner_id)
        .order_by(Document.created_at.desc(), Document.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(documents), total


def get_document(session: Session, owner_id: uuid.UUID, document_id: uuid.UUID) -> Document:
    document = session.scalar(
        select(Document).where(Document.id == document_id, Document.owner_id == owner_id)
    )
    if document is None:
        raise NotFoundError(NOT_FOUND_MESSAGE)
    return document


def delete_document(session: Session, owner_id: uuid.UUID, document_id: uuid.UUID) -> None:
    """Deletes the document; the database cascade removes its bytes, jobs, chunks and vectors."""
    deleted = session.scalar(
        delete(Document)
        .where(Document.id == document_id, Document.owner_id == owner_id)
        .returning(Document.id)
    )
    if deleted is None:
        raise NotFoundError(NOT_FOUND_MESSAGE)
    session.commit()

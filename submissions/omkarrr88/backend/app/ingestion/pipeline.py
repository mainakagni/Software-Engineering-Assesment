"""Turns one queued document into embedded chunks.

`prepare_document` does the slow part (extract, chunk, embed) without holding any transaction open.
`store_prepared` writes the result; the worker calls it inside the transaction that also marks the
job done, after checking that the job is still its own.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.models import Chunk, Document, DocumentBlob
from app.documents.validation import KIND_BY_CONTENT_TYPE
from app.ingestion.chunking import Chunk as TextChunk
from app.ingestion.chunking import chunk_document, embedding_text
from app.ingestion.extract import ExtractedText, ExtractionError, extract_pdf, extract_plain
from app.providers.embeddings import Embedder


@dataclass(frozen=True)
class PreparedDocument:
    document_id: uuid.UUID
    owner_id: uuid.UUID
    chunks: list[TextChunk]
    vectors: list[list[float]]
    page_count: int | None


def prepare_document(
    session_factory: sessionmaker[Session],
    document_id: uuid.UUID,
    embedder: Embedder,
    settings: Settings,
) -> PreparedDocument | None:
    """Extracts, chunks and embeds the document. None if it was deleted in the meantime.

    Raises ExtractionError for files that can never be processed and ProviderError when embedding
    fails; the caller decides between retrying and failing the job.
    """
    with session_factory() as session:
        row = session.execute(
            select(Document.owner_id, Document.filename, Document.content_type, DocumentBlob.data)
            .join(DocumentBlob, DocumentBlob.document_id == Document.id)
            .where(Document.id == document_id)
        ).one_or_none()
    if row is None:
        return None
    owner_id, filename, content_type, data = row

    extracted = _extract(content_type, data, settings)
    chunks = chunk_document(
        extracted.pages,
        markdown=KIND_BY_CONTENT_TYPE.get(content_type) == "markdown",
        size=settings.chunk_size_chars,
        overlap=settings.chunk_overlap_chars,
    )
    limit = settings.max_chunks_per_document
    if len(chunks) > limit:
        # Checked before anything is embedded, so a document that is too long spends no quota.
        raise ExtractionError(
            f"The document is too long: it splits into {len(chunks):,} passages, and the limit "
            f"is {limit:,}. Upload a shorter document or a part of it."
        )
    vectors = embedder.embed_documents([embedding_text(c) for c in chunks], title=filename)
    return PreparedDocument(
        document_id=document_id,
        owner_id=owner_id,
        chunks=chunks,
        vectors=vectors,
        page_count=extracted.page_count,
    )


def store_prepared(session: Session, prepared: PreparedDocument) -> bool:
    """Writes the chunks and marks the document ready. False if the document is gone.

    Must run inside the caller's transaction.
    """
    # Lock the row: if the user deleted the document while it was being embedded, it is gone
    # together with its job and blob (cascade), and there is nothing to store.
    still_there = session.scalar(
        select(Document.id).where(Document.id == prepared.document_id).with_for_update()
    )
    if still_there is None:
        return False
    session.execute(delete(Chunk).where(Chunk.document_id == prepared.document_id))
    session.execute(
        insert(Chunk),
        [
            {
                "document_id": prepared.document_id,
                "owner_id": prepared.owner_id,
                "chunk_index": chunk.index,
                "text": chunk.text,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "section": chunk.section,
                "char_count": len(chunk.text),
                "embedding": vector,
            }
            for chunk, vector in zip(prepared.chunks, prepared.vectors, strict=True)
        ],
    )
    session.execute(
        update(Document)
        .where(Document.id == prepared.document_id)
        .values(
            status="ready",
            error=None,
            chunk_count=len(prepared.chunks),
            page_count=prepared.page_count,
            processed_at=func.now(),
            updated_at=func.now(),
        )
    )
    # The original bytes are not needed any more; the free database is small.
    session.execute(delete(DocumentBlob).where(DocumentBlob.document_id == prepared.document_id))
    return True


def _extract(content_type: str, data: bytes, settings: Settings) -> ExtractedText:
    kind = KIND_BY_CONTENT_TYPE.get(content_type)
    if kind == "pdf":
        return extract_pdf(data, max_pages=settings.max_pdf_pages)
    if kind in ("text", "markdown"):
        return extract_plain(data)
    raise ExtractionError("This file type is not supported.")

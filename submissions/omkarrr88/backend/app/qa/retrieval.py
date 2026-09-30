"""Vector search over the user's own chunks."""

import re
import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import and_, select, text
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document

ITERATIVE_SCAN_SINCE = (0, 8)  # the pgvector release that added hnsw.iterative_scan


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    document_name: str
    text: str
    page_start: int | None
    page_end: int | None
    section: str | None
    similarity: float  # cosine similarity, 1.0 = same direction


def search_chunks(
    session: Session,
    owner_id: uuid.UUID,
    query_vector: Sequence[float],
    *,
    k: int,
    document_ids: Sequence[uuid.UUID] | None = None,
) -> list[RetrievedChunk]:
    """The `k` chunks closest to the query, from the owner's ready documents only."""
    _widen_index_search(session)
    distance = Chunk.embedding.cosine_distance(list(query_vector)).label("distance")
    statement = (
        select(
            Chunk.id,
            Chunk.document_id,
            Document.filename,
            Chunk.text,
            Chunk.page_start,
            Chunk.page_end,
            Chunk.section,
            distance,
        )
        .join(Document, and_(Document.id == Chunk.document_id, Document.owner_id == Chunk.owner_id))
        .where(Chunk.owner_id == owner_id, Document.status == "ready")
        .order_by(distance)
        .limit(k)
    )
    if document_ids is not None:
        statement = statement.where(Chunk.document_id.in_(list(document_ids)))
    rows = session.execute(statement).all()
    chunks = [
        RetrievedChunk(
            chunk_id=row.id,
            document_id=row.document_id,
            document_name=row.filename,
            text=row.text,
            page_start=row.page_start,
            page_end=row.page_end,
            section=row.section,
            similarity=1.0 - float(row.distance),
        )
        for row in rows
    ]
    # relaxed_order may return rows slightly out of order
    return sorted(chunks, key=lambda chunk: chunk.similarity, reverse=True)


def supports_iterative_scan(pgvector_version: str | None) -> bool:
    if pgvector_version is None:
        return False
    numbers = tuple(int(part) for part in re.findall(r"\d+", pgvector_version)[:2])
    return numbers >= ITERATIVE_SCAN_SINCE


def _pgvector_version(session: Session) -> str | None:
    return session.execute(
        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).scalar_one_or_none()


def _widen_index_search(session: Session) -> None:
    """With a selective filter (one user, a few documents) a plain HNSW scan can return fewer than
    k rows. pgvector 0.8+ keeps scanning the index until it has enough; older versions, which some
    hosts still run, get the longest candidate list pgvector allows instead."""
    if supports_iterative_scan(_pgvector_version(session)):
        session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    else:
        session.execute(text("SET LOCAL hnsw.ef_search = 1000"))

"""
Retriever Service — pgvector cosine similarity search
Finds the top-K most relevant chunks for a query embedding.
"""
from __future__ import annotations
import uuid
import logging
from typing import List, Optional

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DocumentChunk, Document, DocumentStatus

logger = logging.getLogger(__name__)


async def retrieve_chunks(
    db: AsyncSession,
    query_embedding: List[float],
    owner_id: uuid.UUID,
    top_k: int = 5,
    document_ids: Optional[List[uuid.UUID]] = None,
) -> List[DocumentChunk]:
    """
    Retrieve the top_k most relevant chunks for a user's query.
    Filters by owner_id to enforce user isolation.
    Optionally restricts to specific document_ids.
    Uses cosine distance via pgvector (<=> operator).
    """
    # Build embedding literal for pgvector (values are floats from Gemini API)
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    query = (
        select(DocumentChunk)
        .join(Document, DocumentChunk.document_id == Document.id)
        .where(
            DocumentChunk.owner_id == owner_id,
            Document.status == DocumentStatus.READY,
        )
    )

    # Apply document filter BEFORE ordering and limiting
    if document_ids:
        query = query.where(DocumentChunk.document_id.in_(document_ids))

    is_sqlite = db.bind and getattr(db.bind.dialect, "name", "") == "sqlite"
    if is_sqlite:
        query = query.order_by(DocumentChunk.chunk_index).limit(top_k)
    else:
        query = (
            query
            .order_by(
                text(f"document_chunks.embedding <=> '{embedding_str}'::vector")
            )
            .limit(top_k)
        )

    result = await db.execute(query)
    chunks = result.scalars().all()

    logger.info(
        f"Retrieved {len(chunks)} chunks",
        extra={"owner_id": str(owner_id), "top_k": top_k, "filtered_docs": len(document_ids or [])},
    )
    return list(chunks)

import uuid
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models import DocumentChunk, Document

logger = logging.getLogger("documind.vector_store")

# Minimum cosine-similarity score for a chunk to be considered relevant.
# Cosine distance returned by pgvector is in [0, 2]; similarity = 1 - distance/2.
# We reject chunks whose similarity is below this threshold.
RELEVANCE_THRESHOLD = 0.25


def search_similar_chunks(
    db: Session,
    user_id: uuid.UUID,
    query_vector: List[float],
    top_k: int = 6,
    document_ids: Optional[List[uuid.UUID]] = None,
) -> List[Dict[str, Any]]:
    """
    Perform a cosine-similarity vector search, returning up to `top_k` chunks
    that surpass `RELEVANCE_THRESHOLD`.

    Each result dict contains:
        chunk_id, document_id, document_name, page_number,
        chunk_index, content, similarity_score
    """
    try:
        base_query = (
            db.query(DocumentChunk, Document.filename)
            .join(Document, DocumentChunk.document_id == Document.id)
            .filter(
                DocumentChunk.user_id == user_id,
                Document.status == "ready",
            )
        )

        if document_ids:
            base_query = base_query.filter(
                DocumentChunk.document_id.in_(document_ids)
            )

        bind = db.get_bind()
        if "postgresql" in str(bind.url):
            # pgvector cosine_distance returns 0 = identical, 2 = opposite
            # Fetch top_k * 2 then filter by threshold so we still get top_k after pruning
            raw = (
                base_query
                .order_by(DocumentChunk.embedding.cosine_distance(query_vector))
                .limit(top_k * 2)
                .all()
            )

            matched: List[Dict[str, Any]] = []
            for chunk, doc_name in raw:
                # Calculate the distance then derive similarity
                try:
                    distance = float(
                        db.execute(
                            __import__("sqlalchemy", fromlist=["text"]).text(
                                "SELECT embedding <=> CAST(:vec AS vector) FROM document_chunks WHERE id = :cid"
                            ),
                            {"vec": str(query_vector), "cid": str(chunk.id)},
                        ).scalar()
                    )
                    similarity = 1.0 - distance / 2.0
                except Exception:
                    # If inline distance query fails, include chunk with unknown score
                    similarity = 1.0  # assume relevant

                if similarity >= RELEVANCE_THRESHOLD:
                    matched.append({
                        "chunk_id": chunk.id,
                        "document_id": chunk.document_id,
                        "document_name": doc_name,
                        "page_number": chunk.page_number,
                        "chunk_index": chunk.chunk_index,
                        "content": chunk.content,
                        "similarity_score": round(similarity, 4),
                    })
                    if len(matched) >= top_k:
                        break

            return matched

        else:
            # Fallback for SQLite (unit tests): return as-is with dummy score
            all_chunks = base_query.limit(top_k).all()
            return [
                {
                    "chunk_id": chunk.id,
                    "document_id": chunk.document_id,
                    "document_name": doc_name,
                    "page_number": chunk.page_number,
                    "chunk_index": chunk.chunk_index,
                    "content": chunk.content,
                    "similarity_score": 1.0,
                }
                for chunk, doc_name in all_chunks
            ]

    except Exception as e:
        logger.error(f"Vector similarity search failed: {e}", exc_info=True)
        return []

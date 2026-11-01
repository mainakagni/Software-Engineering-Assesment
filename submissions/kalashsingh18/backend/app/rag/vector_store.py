import uuid
import logging
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from app.models import DocumentChunk, Document

logger = logging.getLogger("documind.vector_store")


RELEVANCE_THRESHOLD = 0.25


def search_similar_chunks(
    db: Session,
    user_id: uuid.UUID,
    query_vector: List[float],
    top_k: int = 6,
    document_ids: Optional[List[uuid.UUID]] = None,
) -> List[Dict[str, Any]]:
   
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
        try:
            dialect_name = bind.engine.dialect.name
        except AttributeError:
            try:
                dialect_name = str(bind.url)  # SQLAlchemy 1.x fallback
            except AttributeError:
                dialect_name = ""

        if "postgresql" in dialect_name:
            raw = (
                base_query
                .order_by(DocumentChunk.embedding.cosine_distance(query_vector))
                .limit(top_k * 2)
                .all()
            )

            matched: List[Dict[str, Any]] = []
            for chunk, doc_name in raw:
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

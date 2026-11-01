import uuid
import time
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session

from app.models.query_log import QueryLog
from app.rag.vector_store import search_similar_chunks
from app.utils.embeddings import get_query_embedding
from app.rag.generator import generate_grounded_answer, REFUSAL_MESSAGE, OUT_OF_CONTEXT_MESSAGE


def answer_question(
    db: Session,
    user_id: uuid.UUID,
    question: str,
    document_ids: Optional[List[uuid.UUID]] = None,
    chat_history: Optional[List[Dict[str, str]]] = None,
) -> Dict[str, Any]:
    """
    Full RAG pipeline:
      1. Embed the query.
      2. Retrieve top-k semantically similar chunks (with relevance threshold).
      3. Generate a grounded answer via the configured LLM provider.
      4. Build citations only from chunks that passed the threshold.
      5. Persist the query log.
    """
    start_time = time.time()

    # 1. Embed the query with the correct task_type=retrieval_query
    query_vector = get_query_embedding(question)

    # 2. Retrieve similar chunks (already filtered by relevance threshold inside vector_store)
    retrieved_chunks = search_similar_chunks(
        db=db,
        user_id=user_id,
        query_vector=query_vector,
        top_k=6,
        document_ids=document_ids,
    )

    # 3. Generate the answer
    answer, usage = generate_grounded_answer(
        question, retrieved_chunks, chat_history=chat_history
    )

    # 4. Build citations — only for non-refusal answers and chunks that were
    #    actually retrieved (all of them already passed RELEVANCE_THRESHOLD).
    is_refusal = answer.strip() in (REFUSAL_MESSAGE, OUT_OF_CONTEXT_MESSAGE)

    citations: List[Dict[str, Any]] = []
    if not is_refusal and retrieved_chunks:
        seen: set = set()
        for c in retrieved_chunks:
            # Deduplicate citations pointing to the same document+page
            key = (str(c["document_id"]), c["page_number"])
            if key in seen:
                continue
            seen.add(key)

            passage = c["content"]
            citations.append({
                "document_id": str(c["document_id"]),
                "document_name": c["document_name"],
                "page_number": c["page_number"],
                "chunk_index": c.get("chunk_index", 0),
                "passage": (passage[:300] + "…") if len(passage) > 300 else passage,
                "similarity_score": c.get("similarity_score", None),
            })

    # 5. Persist the query log
    log = QueryLog(
        user_id=user_id,
        question=question,
        answer=answer,
        citations=citations,
        prompt_tokens=usage["prompt_tokens"],
        completion_tokens=usage["completion_tokens"],
        latency_ms=usage["latency_ms"],
        estimated_cost=usage["estimated_cost_usd"],
    )
    db.add(log)
    db.commit()

    return {
        "question": question,
        "answer": answer,
        "citations": citations,
        "usage": usage,
        "grounded": not is_refusal,
        "chunks_retrieved": len(retrieved_chunks),
    }


def get_user_query_history(
    db: Session, user_id: uuid.UUID, limit: int = 50
) -> List[QueryLog]:
    return (
        db.query(QueryLog)
        .filter(QueryLog.user_id == user_id)
        .order_by(QueryLog.created_at.desc())
        .limit(limit)
        .all()
    )

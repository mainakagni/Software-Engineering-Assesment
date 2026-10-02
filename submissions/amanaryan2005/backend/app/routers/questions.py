"""
Questions Router — ask questions, get history
POST /api/v1/questions       Ask a question (RAG pipeline)
GET  /api/v1/questions       Get question history
"""
import logging
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.auth import get_current_user
from app.config import settings
from app.database import get_db
from app.models import Document, DocumentChunk, DocumentStatus, QuestionHistory, User
from app.schemas import AskRequest, AskResponse, Citation, QuestionHistoryItem, QuestionHistoryResponse
from app.services.embedder import embed_query
from app.services.retriever import retrieve_chunks
from app.services.llm import generate_answer

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/questions", tags=["Questions"])
limiter = Limiter(key_func=get_remote_address)


@router.post("", response_model=AskResponse, status_code=status.HTTP_200_OK)
@limiter.limit(f"{settings.rate_limit_questions_per_minute}/minute")
async def ask_question(
    request: Request,
    body: AskRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Ask a question using the RAG pipeline:
    1. Embed the query
    2. Retrieve top-K relevant chunks from pgvector
    3. Generate a grounded answer with Gemini
    4. Store the Q&A in history
    5. Return answer + citations + usage
    """
    request_id = str(uuid.uuid4())
    logger.info(
        "Question received",
        extra={"request_id": request_id, "user_id": str(current_user.id), "question": body.question[:100]},
    )

    # Validate document_ids belong to this user
    if body.document_ids:
        for doc_id in body.document_ids:
            doc = await db.get(Document, doc_id)
            if not doc or doc.owner_id != current_user.id:
                raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
            if doc.status != DocumentStatus.READY:
                raise HTTPException(
                    status_code=400,
                    detail=f"Document '{doc.original_filename}' is not ready (status: {doc.status})",
                )

    # Embed query
    try:
        query_embedding = await embed_query(body.question)
    except Exception as exc:
        logger.error(f"Embedding failed: {exc}", extra={"request_id": request_id})
        raise HTTPException(status_code=502, detail="Embedding service unavailable. Please retry.")

    # Retrieve chunks
    chunks = await retrieve_chunks(
        db=db,
        query_embedding=query_embedding,
        owner_id=current_user.id,
        top_k=settings.top_k_chunks,
        document_ids=[d for d in body.document_ids] if body.document_ids else None,
    )

    # Build document name lookup
    doc_name_map: dict = {}
    if chunks:
        doc_ids = list({c.document_id for c in chunks})
        doc_result = await db.execute(select(Document).where(Document.id.in_(doc_ids)))
        for doc in doc_result.scalars().all():
            doc_name_map[str(doc.id)] = doc.original_filename

    # Generate answer
    try:
        llm_result = await generate_answer(
            question=body.question,
            chunks=chunks,
            document_names=doc_name_map,
        )
    except Exception as exc:
        logger.error(f"LLM generation failed: {exc}", extra={"request_id": request_id})
        raise HTTPException(status_code=502, detail="Language model unavailable. Please retry.")

    # Build citations
    citations = []
    if not llm_result.was_refused:
        for chunk in chunks:
            citations.append(Citation(
                document_name=doc_name_map.get(str(chunk.document_id), "Unknown"),
                passage=chunk.content[:300] + ("…" if len(chunk.content) > 300 else ""),
                page_number=chunk.page_number,
                chunk_id=str(chunk.id),
            ))

    # Save to history
    history_entry = QuestionHistory(
        user_id=current_user.id,
        question=body.question,
        answer=llm_result.answer,
        citations=[c.model_dump() for c in citations],
        document_ids=[str(d) for d in (body.document_ids or [])],
        tokens_used=llm_result.tokens_used,
        latency_ms=llm_result.latency_ms,
        estimated_cost_usd=llm_result.estimated_cost_usd,
        was_refused=llm_result.was_refused,
    )
    db.add(history_entry)
    await db.commit()
    await db.refresh(history_entry)

    logger.info(
        "Question answered",
        extra={
            "request_id": request_id,
            "question_id": str(history_entry.id),
            "refused": llm_result.was_refused,
            "latency_ms": llm_result.latency_ms,
        },
    )

    return AskResponse(
        question_id=history_entry.id,
        question=body.question,
        answer=llm_result.answer,
        citations=citations,
        was_refused=llm_result.was_refused,
        tokens_used=llm_result.tokens_used,
        latency_ms=llm_result.latency_ms,
        estimated_cost_usd=llm_result.estimated_cost_usd,
    )


@router.get("", response_model=QuestionHistoryResponse)
async def get_history(
    skip: int = 0,
    limit: int = 20,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve paginated question history for the authenticated user."""
    total_result = await db.execute(
        select(func.count()).select_from(QuestionHistory).where(QuestionHistory.user_id == current_user.id)
    )
    total = total_result.scalar_one()

    result = await db.execute(
        select(QuestionHistory)
        .where(QuestionHistory.user_id == current_user.id)
        .order_by(QuestionHistory.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    items = result.scalars().all()
    return QuestionHistoryResponse(
        items=[QuestionHistoryItem.model_validate(q) for q in items],
        total=total,
    )

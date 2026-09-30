"""Answering a question: check the scope, retrieve, generate, check the citations, store.

`answer_question` is the pipeline itself and stores nothing, so an offline evaluation can run
exactly what the API runs. `ask` adds the ownership checks, the answer cache and the history.

No transaction stays open during a provider call: the reads before each call end with a commit,
which returns the connection to the pool while the embedding service or the model works.
"""

import logging
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Document, Question
from app.errors import ConflictError, NotFoundError, ServiceUnavailableError
from app.providers.embeddings import Embedder
from app.providers.errors import ProviderError
from app.providers.llm import LLMClient, LLMResult
from app.providers.retry import call_with_retries
from app.qa.cache import cache_key, find_cached
from app.qa.cost import estimate_cost_usd, estimate_tokens
from app.qa.grounding import NOT_FOUND_ANSWER, GroundedAnswer, ModelReply, ground, parse_reply
from app.qa.prompt import ANSWER_SCHEMA, SYSTEM_PROMPT, build_user_prompt
from app.qa.retrieval import RetrievedChunk, search_chunks

logger = logging.getLogger(__name__)

NO_DOCUMENTS_ANSWER = "You have no processed documents yet. Upload one and wait until it is ready."
Refusal = Literal["no_documents", "retrieval", "grounding"]


@dataclass(frozen=True)
class AnswerResult:
    grounded: GroundedAnswer
    retrieved: list[RetrievedChunk]
    reply: ModelReply | None  # None when the model was not called
    usage: dict[str, Any]
    refused_by: Refusal | None


def ask(
    session: Session,
    user_id: uuid.UUID,
    question: str,
    document_ids: Sequence[uuid.UUID] | None,
    *,
    embedder: Embedder,
    llm: LLMClient,
    settings: Settings,
) -> Question:
    started = time.perf_counter()
    _check_selection(session, user_id, document_ids)
    has_documents = document_ids is not None or _has_ready_documents(session, user_id)
    key: str | None = None
    earlier: Question | None = None
    if has_documents and settings.answer_cache_ttl_hours > 0:
        key = cache_key(session, user_id, question, document_ids, settings)
        earlier = find_cached(session, user_id, key, ttl_hours=settings.answer_cache_ttl_hours)
    session.commit()

    if earlier is not None:
        record = _store_copy(session, user_id, question, document_ids, earlier, started)
        logger.info(
            "qa.cache_hit", extra={"question_id": str(record.id), "original_id": str(earlier.id)}
        )
        return record
    if not has_documents:
        result = _refusal(NO_DOCUMENTS_ANSWER, "no_documents", started)
    else:
        result = answer_question(
            session, user_id, question, document_ids,
            embedder=embedder, llm=llm, settings=settings, started=started,
        )  # fmt: skip
    # Only answers that were found are offered to the cache (see app.qa.cache).
    record = _store(
        session, user_id, question, document_ids, result,
        key=key if result.grounded.found else None,
    )  # fmt: skip
    _log_answer(record, result)
    return record


def answer_question(
    session: Session,
    user_id: uuid.UUID,
    question: str,
    document_ids: Sequence[uuid.UUID] | None,
    *,
    embedder: Embedder,
    llm: LLMClient,
    settings: Settings,
    started: float | None = None,
) -> AnswerResult:
    started = time.perf_counter() if started is None else started
    retrieval_started = time.perf_counter()
    try:
        query_vector = embedder.embed_query(question)
    except ProviderError as exc:
        raise _unavailable(exc, code="embedding_unavailable", service="embedding service") from exc
    chunks = search_chunks(
        session, user_id, query_vector, k=settings.retrieval_top_k, document_ids=document_ids
    )
    session.commit()
    retrieval_ms = _ms_since(retrieval_started)
    embedding_tokens = estimate_tokens(question)

    # Gate 1: nothing close enough to the question, so the model is not asked at all.
    if not chunks or chunks[0].similarity < settings.min_similarity:
        usage = _usage(
            None, embedding_tokens, retrieval_ms, generation_ms=0, started=started,
            settings=settings,
        )  # fmt: skip
        grounded = GroundedAnswer(found=False, answer=NOT_FOUND_ANSWER, citations=[])
        return AnswerResult(grounded, chunks, None, usage, refused_by="retrieval")

    prompt, sources = build_user_prompt(question, chunks)
    generation_started = time.perf_counter()
    reply, llm_result = _generate(llm, prompt, settings)
    generation_ms = _ms_since(generation_started)
    # Gate 2: the answer must cite a passage that was sent, with a quote found in it.
    grounded = ground(reply, sources)
    usage = _usage(
        llm_result,
        embedding_tokens,
        retrieval_ms,
        generation_ms,
        started=started,
        settings=settings,
    )
    refused_by: Refusal | None = None if grounded.found else "grounding"
    return AnswerResult(grounded, chunks, reply, usage, refused_by)


def list_questions(
    session: Session, user_id: uuid.UUID, *, limit: int, offset: int
) -> tuple[list[Question], int]:
    total = session.scalar(select(func.count()).where(Question.user_id == user_id)) or 0
    rows = session.scalars(
        select(Question)
        .where(Question.user_id == user_id)
        .order_by(Question.created_at.desc(), Question.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def get_question(session: Session, user_id: uuid.UUID, question_id: uuid.UUID) -> Question:
    record = session.scalar(
        select(Question).where(Question.id == question_id, Question.user_id == user_id)
    )
    if record is None:
        raise NotFoundError("Question not found.")
    return record


# --- helpers ------------------------------------------------------------------------------------


def _check_selection(
    session: Session, user_id: uuid.UUID, document_ids: Sequence[uuid.UUID] | None
) -> None:
    if document_ids is None:
        return
    statuses = session.execute(
        select(Document.id, Document.status).where(
            Document.owner_id == user_id, Document.id.in_(list(document_ids))
        )
    ).all()
    if len(statuses) != len(document_ids):  # someone else's IDs look exactly like missing ones
        raise NotFoundError("One or more of the selected documents do not exist.")
    if any(status != "ready" for _, status in statuses):
        raise ConflictError("Some of the selected documents are not ready yet.")


def _has_ready_documents(session: Session, user_id: uuid.UUID) -> bool:
    ready = exists().where(Document.owner_id == user_id, Document.status == "ready")
    return bool(session.scalar(select(ready)))


def _generate(llm: LLMClient, prompt: str, settings: Settings) -> tuple[ModelReply, LLMResult]:
    def attempt() -> tuple[ModelReply, LLMResult]:
        result = llm.generate_json(SYSTEM_PROMPT, prompt, ANSWER_SCHEMA)
        return parse_reply(result.text), result

    try:
        return call_with_retries(
            attempt,
            max_retries=settings.provider_max_retries,
            max_wait_seconds=settings.provider_max_retry_wait_seconds,
        )
    except ProviderError as exc:
        raise _unavailable(exc, code="llm_unavailable", service="language model") from exc


def _unavailable(error: ProviderError, *, code: str, service: str) -> ServiceUnavailableError:
    logger.warning(
        "qa.provider_failed",
        extra={"code": code, "kind": error.kind, "provider_message": error.message},
    )
    if error.kind == "quota_exhausted":
        message = f"The demo has used up today's {service} quota. Please try again tomorrow."
    elif error.kind == "bad_request":
        message = f"The {service} could not process this question."
    else:
        message = f"The {service} is not responding. Please try again in a minute."
    return ServiceUnavailableError(code, message)


def _usage(
    llm_result: LLMResult | None,
    embedding_tokens: int,
    retrieval_ms: int,
    generation_ms: int,
    *,
    started: float,
    settings: Settings,
) -> dict[str, Any]:
    prompt_tokens = llm_result.prompt_tokens if llm_result else 0
    output_tokens = llm_result.output_tokens if llm_result else 0
    thinking_tokens = llm_result.thinking_tokens if llm_result else 0
    return {
        "model": llm_result.model if llm_result else None,
        "prompt_tokens": prompt_tokens,
        "output_tokens": output_tokens,
        "thinking_tokens": thinking_tokens,
        "total_tokens": prompt_tokens + output_tokens + thinking_tokens,
        "embedding_tokens": embedding_tokens,
        "retrieval_ms": retrieval_ms,
        "generation_ms": generation_ms,
        "latency_ms": _ms_since(started),
        "estimated_cost_usd": estimate_cost_usd(
            prompt_tokens=prompt_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            embedding_tokens=embedding_tokens,
            settings=settings,
        ),
    }


def _no_usage(started: float) -> dict[str, Any]:
    """Usage of an answer that called no provider."""
    return {
        "model": None, "prompt_tokens": 0, "output_tokens": 0, "thinking_tokens": 0,
        "total_tokens": 0, "embedding_tokens": 0, "retrieval_ms": 0, "generation_ms": 0,
        "latency_ms": _ms_since(started), "estimated_cost_usd": 0.0,
    }  # fmt: skip


def _refusal(answer: str, refused_by: Refusal, started: float) -> AnswerResult:
    grounded = GroundedAnswer(found=False, answer=answer, citations=[])
    return AnswerResult(grounded, [], None, _no_usage(started), refused_by)


def _log_answer(record: Question, result: AnswerResult) -> None:
    citations = result.grounded.citations
    logger.info(
        "qa.answered",
        extra={
            "question_id": str(record.id),
            "found": result.grounded.found,
            "refused_by": result.refused_by,
            "citations": len(citations),
            "verified_citations": sum(c.quote_verified for c in citations),
            "top_similarity": round(result.retrieved[0].similarity, 4)
            if result.retrieved
            else None,
            "latency_ms": result.usage["latency_ms"],
            "prompt_tokens": result.usage["prompt_tokens"],
            "output_tokens": result.usage["output_tokens"],
        },
    )


def _store(
    session: Session,
    user_id: uuid.UUID,
    question: str,
    document_ids: Sequence[uuid.UUID] | None,
    result: AnswerResult,
    *,
    key: str | None,
) -> Question:
    citations = [
        {
            "source_id": c.source_id,
            "document_id": str(c.chunk.document_id),
            "document_name": c.chunk.document_name,
            "page_start": c.chunk.page_start,
            "page_end": c.chunk.page_end,
            "section": c.chunk.section,
            "passage": c.chunk.text,  # a snapshot: history survives deleting the document
            "quote": c.quote,
            "quote_verified": c.quote_verified,
            "score": round(c.chunk.similarity, 4),
        }
        for c in result.grounded.citations
    ]
    record = Question(
        user_id=user_id,
        question=question,
        answer=result.grounded.answer,
        found=result.grounded.found,
        document_ids=list(document_ids) if document_ids is not None else None,
        citations=citations,
        usage=result.usage,
        cache_key=key,
    )
    session.add(record)
    session.commit()
    return record


def _store_copy(
    session: Session,
    user_id: uuid.UUID,
    question: str,
    document_ids: Sequence[uuid.UUID] | None,
    earlier: Question,
    started: float,
) -> Question:
    """A cached answer, stored as its own history entry. Nothing was retrieved or generated."""
    record = Question(
        user_id=user_id,
        question=question,
        answer=earlier.answer,
        found=earlier.found,
        cached=True,
        document_ids=list(document_ids) if document_ids is not None else None,
        citations=earlier.citations,
        usage=_no_usage(started),
    )
    session.add(record)
    session.commit()
    return record


def _ms_since(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)

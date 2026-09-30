"""The answer cache: the same question over the same documents gets the stored answer.

The key covers the normalised question, the document selection, a fingerprint of the ready
documents in scope (their IDs and when they were processed), the prompt and the settings that shape
an answer. Uploading, deleting or reprocessing a document changes the fingerprint, so a stale answer
is never served.

Only answers that were found are reused: a refusal may have been bad luck, and asking again is
cheap when retrieval already refuses. Copies are never reused either, so an answer's age counts
from when the model wrote it.

A document deleted while a question is being answered can leave an answer stored under a key that
still lists it. No later request can produce that key again, because the document is gone, so the
entry is never served.
"""

import hashlib
import json
import uuid
from collections.abc import Sequence
from datetime import timedelta

from sqlalchemy import func, select, true
from sqlalchemy.orm import Session

from app.config import Settings
from app.db.models import Document, Question
from app.qa.prompt import SYSTEM_PROMPT

_PROMPT_FINGERPRINT = hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest()[:16]


def normalise_question(question: str) -> str:
    return " ".join(question.casefold().split()).rstrip(" ?!.")


def cache_key(
    session: Session,
    user_id: uuid.UUID,
    question: str,
    document_ids: Sequence[uuid.UUID] | None,
    settings: Settings,
) -> str:
    in_scope = Document.id.in_(list(document_ids)) if document_ids is not None else true()
    documents = session.execute(
        select(Document.id, Document.processed_at)
        .where(Document.owner_id == user_id, Document.status == "ready", in_scope)
        .order_by(Document.id)
    ).all()
    payload = {
        "question": normalise_question(question),
        "scope": sorted(str(i) for i in document_ids) if document_ids is not None else "all",
        "documents": [f"{row.id}:{row.processed_at}" for row in documents],
        "settings": [
            _PROMPT_FINGERPRINT,
            settings.llm_model,
            settings.embedding_model,
            settings.retrieval_top_k,
            settings.retrieval_min_similarity,
        ],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def find_cached(
    session: Session, user_id: uuid.UUID, key: str, *, ttl_hours: int
) -> Question | None:
    return session.scalar(
        select(Question)
        .where(
            Question.user_id == user_id,
            Question.cache_key == key,
            Question.found.is_(True),
            Question.cached.is_(False),
            Question.created_at > func.now() - timedelta(hours=ttl_hours),
        )
        .order_by(Question.created_at.desc())
        .limit(1)
    )

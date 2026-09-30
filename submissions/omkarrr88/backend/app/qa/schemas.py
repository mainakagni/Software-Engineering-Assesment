import uuid
from datetime import datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

MAX_SELECTED_DOCUMENTS = 20


def _clean_question(value: str) -> str:
    question = " ".join(value.split())
    if len(question) < 3:
        raise ValueError("Ask a question of at least 3 characters.")
    return question


def _unique(ids: list[uuid.UUID] | None) -> list[uuid.UUID] | None:
    if ids is None:
        return None
    if not ids:  # an empty selection would search nothing; asking for all is spelled null
        raise ValueError("Select at least one document, or leave document_ids out to search all.")
    return list(dict.fromkeys(ids))


class AskRequest(BaseModel):
    question: Annotated[str, AfterValidator(_clean_question)] = Field(
        max_length=1000, examples=["How many days in advance should flights be booked?"]
    )
    document_ids: Annotated[list[uuid.UUID] | None, AfterValidator(_unique)] = Field(
        default=None,
        max_length=MAX_SELECTED_DOCUMENTS,
        description="Search only these documents. Leave out to search all your ready documents.",
    )


class CitationOut(BaseModel):
    source_id: str
    document_id: uuid.UUID
    document_name: str
    page_start: int | None
    page_end: int | None
    section: str | None
    passage: str = Field(description="The retrieved passage the quote comes from.")
    quote: str
    quote_verified: bool = Field(description="The quote was found in the passage.")
    score: float = Field(description="Cosine similarity between the question and the passage.")


class UsageOut(BaseModel):
    model: str | None
    prompt_tokens: int
    output_tokens: int
    thinking_tokens: int
    total_tokens: int
    embedding_tokens: int
    retrieval_ms: int
    generation_ms: int
    latency_ms: int
    estimated_cost_usd: float


class AnswerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    question: str
    answer: str
    found: bool
    document_ids: list[uuid.UUID] | None = Field(description="The selection, if one was given.")
    citations: list[CitationOut]
    usage: UsageOut
    created_at: datetime

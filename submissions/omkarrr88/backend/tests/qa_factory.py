"""Retrieved chunks for tests of the answering code, without a database."""

import uuid
from typing import Any

from app.qa.retrieval import RetrievedChunk

PASSAGE = (
    "Domestic flights should be booked at least 7 business days in advance. "
    "International flights must be booked at least 14 business days in advance."
)


def make_chunk(text: str = PASSAGE, **overrides: Any) -> RetrievedChunk:
    values: dict[str, Any] = {
        "chunk_id": uuid.uuid4(),
        "document_id": uuid.uuid4(),
        "document_name": "travel.md",
        "text": text,
        "page_start": None,
        "page_end": None,
        "section": "Travel > Flights",
        "similarity": 0.8,
    }
    values.update(overrides)
    return RetrievedChunk(**values)

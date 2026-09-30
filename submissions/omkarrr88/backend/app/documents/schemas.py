import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    status: Literal["queued", "processing", "ready", "failed"]
    error: str | None = Field(description="Why processing failed, when status is failed.")
    page_count: int | None = Field(description="Pages in the PDF; null for text files.")
    chunk_count: int | None
    created_at: datetime
    updated_at: datetime

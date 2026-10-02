"""
Pydantic Schemas — Request/Response models
"""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, EmailStr, Field, ConfigDict

from app.models import DocumentStatus


# ── Auth ──────────────────────────────────────────────────────────────────────

class SignupRequest(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(..., min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str  # accepts username or email
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    email: str
    username: str
    created_at: datetime


# ── Documents ─────────────────────────────────────────────────────────────────

class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    filename: str
    original_filename: str
    file_size: int
    mime_type: str
    status: DocumentStatus
    error_message: Optional[str] = None
    chunk_count: Optional[int] = None
    created_at: datetime
    processed_at: Optional[datetime] = None


class DocumentListResponse(BaseModel):
    items: List[DocumentResponse]
    total: int


# ── Q&A ───────────────────────────────────────────────────────────────────────

class Citation(BaseModel):
    document_name: str
    passage: str
    page_number: Optional[int] = None
    chunk_id: str


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=2000)
    document_ids: Optional[List[uuid.UUID]] = Field(
        default=None,
        description="If provided, restrict to these documents only. Otherwise, search all ready documents.",
    )


class AskResponse(BaseModel):
    question_id: uuid.UUID
    question: str
    answer: str
    citations: List[Citation]
    was_refused: bool
    tokens_used: Optional[int] = None
    latency_ms: Optional[float] = None
    estimated_cost_usd: Optional[float] = None


class QuestionHistoryItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    question: str
    answer: Optional[str] = None
    citations: List[Dict[str, Any]] = []
    was_refused: bool
    tokens_used: Optional[int] = None
    latency_ms: Optional[float] = None
    created_at: datetime


class QuestionHistoryResponse(BaseModel):
    items: List[QuestionHistoryItem]
    total: int


# ── Health ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    database: str
    vector_store: str
    worker_queue: str
    version: str = "1.0.0"

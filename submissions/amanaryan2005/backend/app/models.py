"""
ORM Models — User, Document, Chunk, QuestionHistory
"""
import uuid
import enum
from datetime import datetime, timezone
from typing import List

from sqlalchemy import (
    Column, String, Text, Boolean, DateTime, Integer, Float,
    ForeignKey, Enum as SAEnum, JSON, Index
)
from sqlalchemy.dialects.postgresql import UUID, JSONB as PG_JSONB
from sqlalchemy.orm import relationship
from pgvector.sqlalchemy import Vector

JSONB = JSON().with_variant(PG_JSONB, "postgresql")

from app.database import Base


class DocumentStatus(str, enum.Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    documents: List["Document"] = relationship("Document", back_populates="owner", cascade="all, delete-orphan")
    questions: List["QuestionHistory"] = relationship("QuestionHistory", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User {self.username}>"


class Document(Base):
    __tablename__ = "documents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String(500), nullable=False)
    original_filename = Column(String(500), nullable=False)
    file_size = Column(Integer, nullable=False)
    mime_type = Column(String(100), nullable=False)
    status = Column(
        SAEnum(DocumentStatus, name="documentstatus"),
        nullable=False,
        default=DocumentStatus.QUEUED,
        index=True,
    )
    error_message = Column(Text, nullable=True)
    chunk_count = Column(Integer, nullable=True)
    celery_task_id = Column(String(255), nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )
    processed_at = Column(DateTime(timezone=True), nullable=True)

    owner: "User" = relationship("User", back_populates="documents")
    chunks: List["DocumentChunk"] = relationship("DocumentChunk", back_populates="document", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Document {self.original_filename} status={self.status}>"


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id = Column(UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    owner_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index = Column(Integer, nullable=False)
    content = Column(Text, nullable=False)
    page_number = Column(Integer, nullable=True)
    embedding = Column(Vector(768), nullable=True)  # Gemini text-embedding-004 dimension
    metadata_ = Column("metadata", JSONB, default=dict)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    document: "Document" = relationship("Document", back_populates="chunks")

    __table_args__ = (
        Index(
            "ix_document_chunks_embedding",
            "embedding",
            postgresql_using="ivfflat",
            postgresql_with={"lists": 100},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )


class QuestionHistory(Base):
    __tablename__ = "question_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=True)
    citations = Column(JSONB, default=list)  # [{document_name, passage, page, chunk_id}]
    document_ids = Column(JSONB, default=list)  # Filtered doc IDs if specified
    tokens_used = Column(Integer, nullable=True)
    latency_ms = Column(Float, nullable=True)
    estimated_cost_usd = Column(Float, nullable=True)
    was_refused = Column(Boolean, default=False)
    error = Column(Text, nullable=True)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
    )

    user: "User" = relationship("User", back_populates="questions")

    def __repr__(self) -> str:
        return f"<Question {self.id} user={self.user_id}>"

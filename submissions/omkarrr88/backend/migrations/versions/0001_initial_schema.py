"""Initial schema: users, documents, chunks with pgvector, ingestion jobs, questions.

Revision ID: 0001
Revises:
Create Date: 2026-09-30
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
TIMESTAMPTZ = sa.DateTime(timezone=True)


def _created_at() -> sa.Column:
    return sa.Column("created_at", TIMESTAMPTZ, server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        _created_at(),
        sa.UniqueConstraint("email", name="uq_users_email"),
        sa.CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
    )

    op.create_table(
        "documents",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "owner_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_documents_owner_id_users"),
            nullable=False,
        ),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("content_type", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.CHAR(64), nullable=False),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("page_count", sa.Integer()),
        sa.Column("chunk_count", sa.Integer()),
        _created_at(),
        sa.Column("updated_at", TIMESTAMPTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("processed_at", TIMESTAMPTZ),
        sa.CheckConstraint(
            "status IN ('queued', 'processing', 'ready', 'failed')", name="ck_documents_status"
        ),
        sa.UniqueConstraint("owner_id", "sha256", name="uq_documents_owner_id_sha256"),
        sa.UniqueConstraint("id", "owner_id", name="uq_documents_id_owner_id"),
    )
    op.create_index(
        "ix_documents_owner_id_created_at", "documents", ["owner_id", sa.text("created_at DESC")]
    )

    op.create_table(
        "document_blobs",
        sa.Column(
            "document_id",
            UUID,
            sa.ForeignKey(
                "documents.id", ondelete="CASCADE", name="fk_document_blobs_document_id_documents"
            ),
            primary_key=True,
        ),
        sa.Column("data", sa.LargeBinary(), nullable=False),
    )

    op.create_table(
        "chunks",
        sa.Column("id", UUID, primary_key=True),
        sa.Column("document_id", UUID, nullable=False),
        sa.Column("owner_id", UUID, nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("page_start", sa.Integer()),
        sa.Column("page_end", sa.Integer()),
        sa.Column("section", sa.Text()),
        sa.Column("char_count", sa.Integer(), nullable=False),
        sa.Column("embedding", Vector(768), nullable=False),
        _created_at(),
        # The chunk's owner must be its document's owner; enforced by the database.
        sa.ForeignKeyConstraint(
            ["document_id", "owner_id"],
            ["documents.id", "documents.owner_id"],
            ondelete="CASCADE",
            name="fk_chunks_document_id_owner_id_documents",
        ),
        sa.UniqueConstraint("document_id", "chunk_index", name="uq_chunks_document_id_chunk_index"),
    )
    op.create_index("ix_chunks_owner_id", "chunks", ["owner_id"])
    op.create_index(
        "ix_chunks_embedding_hnsw",
        "chunks",
        ["embedding"],
        postgresql_using="hnsw",
        postgresql_ops={"embedding": "vector_cosine_ops"},
    )

    op.create_table(
        "ingestion_jobs",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "document_id",
            UUID,
            sa.ForeignKey(
                "documents.id", ondelete="CASCADE", name="fk_ingestion_jobs_document_id_documents"
            ),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("run_after", TIMESTAMPTZ, server_default=sa.func.now(), nullable=False),
        sa.Column("locked_at", TIMESTAMPTZ),
        sa.Column("locked_by", sa.Text()),
        sa.Column("last_error", sa.Text()),
        sa.Column("request_id", sa.Text()),
        _created_at(),
        sa.Column("updated_at", TIMESTAMPTZ, server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'done', 'failed')", name="ck_ingestion_jobs_status"
        ),
    )
    op.create_index("ix_ingestion_jobs_document_id", "ingestion_jobs", ["document_id"])
    op.create_index(
        "ix_ingestion_jobs_queued_run_after",
        "ingestion_jobs",
        ["run_after"],
        postgresql_where=sa.text("status = 'queued'"),
    )

    op.create_table(
        "questions",
        sa.Column("id", UUID, primary_key=True),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE", name="fk_questions_user_id_users"),
            nullable=False,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("found", sa.Boolean(), nullable=False),
        sa.Column("document_ids", postgresql.ARRAY(UUID)),
        sa.Column(
            "citations",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "usage", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False
        ),
        sa.Column("cache_key", sa.Text()),
        _created_at(),
    )
    op.create_index(
        "ix_questions_user_id_created_at", "questions", ["user_id", sa.text("created_at DESC")]
    )
    op.create_index("ix_questions_user_id_cache_key", "questions", ["user_id", "cache_key"])

    op.create_table(
        "rate_limit_counters",
        sa.Column("key", sa.Text(), primary_key=True),
        sa.Column("window_start", TIMESTAMPTZ, primary_key=True),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    op.create_index("ix_rate_limit_counters_window_start", "rate_limit_counters", ["window_start"])

    op.create_table(
        "worker_heartbeats",
        sa.Column("worker_id", sa.Text(), primary_key=True),
        sa.Column("hostname", sa.Text(), nullable=False),
        sa.Column("started_at", TIMESTAMPTZ, nullable=False),
        sa.Column("last_seen_at", TIMESTAMPTZ, nullable=False),
    )


def downgrade() -> None:
    for table in (
        "worker_heartbeats",
        "rate_limit_counters",
        "questions",
        "ingestion_jobs",
        "chunks",
        "document_blobs",
        "documents",
        "users",
    ):
        op.drop_table(table)

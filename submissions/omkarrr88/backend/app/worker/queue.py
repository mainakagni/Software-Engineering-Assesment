"""The ingestion job queue, kept in Postgres.

Claiming uses FOR UPDATE SKIP LOCKED, so any number of workers can poll the same table without
taking the same job twice. Each state change updates the job and its document in one transaction,
so the status a user sees always matches the job.

A claim is a lease: the claiming worker's ID and the claim time. Every later change to the job
checks that the lease is still the same, so a worker whose job was handed to another worker (after
it looked dead) cannot overwrite that worker's result.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, and_, delete, exists, func, select, text, update
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Document, DocumentBlob, IngestionJob, WorkerHeartbeat
from app.ingestion.pipeline import PreparedDocument, store_prepared


@dataclass(frozen=True)
class ClaimedJob:
    id: uuid.UUID
    document_id: uuid.UUID
    attempts: int  # including the one that is starting now
    request_id: str | None
    worker_id: str
    locked_at: datetime


_CLAIM = text(
    """
    UPDATE ingestion_jobs
    SET status = 'running', attempts = attempts + 1, locked_at = clock_timestamp(),
        locked_by = :worker_id, updated_at = now()
    WHERE id = (
        SELECT id FROM ingestion_jobs
        WHERE status = 'queued' AND run_after <= now()
        ORDER BY run_after, created_at
        FOR UPDATE SKIP LOCKED
        LIMIT 1
    )
    RETURNING id, document_id, attempts, request_id, locked_at
    """
)


def claim_next_job(session_factory: sessionmaker[Session], worker_id: str) -> ClaimedJob | None:
    with session_factory.begin() as session:
        row = session.execute(_CLAIM, {"worker_id": worker_id}).one_or_none()
        if row is None:
            return None
        job = ClaimedJob(
            id=row.id,
            document_id=row.document_id,
            attempts=row.attempts,
            request_id=row.request_id,
            worker_id=worker_id,
            locked_at=row.locked_at,
        )
        _set_document(session, job.document_id, status="processing", error=None)
        return job


def complete_job(
    session_factory: sessionmaker[Session], job: ClaimedJob, prepared: PreparedDocument
) -> bool:
    """Stores the result and marks the job done. False if the job or document is no longer ours."""
    with session_factory.begin() as session:
        if not _lock_if_still_ours(session, job) or not store_prepared(session, prepared):
            return False
        session.execute(
            update(IngestionJob)
            .where(IngestionJob.id == job.id)
            .values(
                status="done",
                locked_at=None,
                locked_by=None,
                last_error=None,
                updated_at=func.now(),
            )
        )
        return True


def retry_job(
    session_factory: sessionmaker[Session], job: ClaimedJob, error: str, delay_seconds: float
) -> bool:
    with session_factory.begin() as session:
        if not _lock_if_still_ours(session, job):
            return False
        session.execute(
            update(IngestionJob)
            .where(IngestionJob.id == job.id)
            .values(
                status="queued",
                run_after=func.now() + timedelta(seconds=delay_seconds),
                locked_at=None,
                locked_by=None,
                last_error=error,
                updated_at=func.now(),
            )
        )
        _set_document(session, job.document_id, status="queued", error=None)
        return True


def fail_job(session_factory: sessionmaker[Session], job: ClaimedJob, reason: str) -> bool:
    """Gives up on the job: the document shows `reason` and its stored bytes are deleted."""
    with session_factory.begin() as session:
        if not _lock_if_still_ours(session, job):
            return False
        _fail(session, job.id, job.document_id, reason)
        return True


def requeue_stale_jobs(
    session_factory: sessionmaker[Session],
    *,
    stale_after: timedelta,
    worker_stale_after: timedelta,
    max_attempts: int,
) -> int:
    """Jobs whose worker died mid-job: retried, or failed if they keep dying.

    A job counts as abandoned only when it has been running for `stale_after` and its worker has
    stopped sending heartbeats, so a long job on a healthy worker is left alone.
    """
    worker_alive = exists().where(
        WorkerHeartbeat.worker_id == IngestionJob.locked_by,
        WorkerHeartbeat.last_seen_at > func.now() - worker_stale_after,
    )
    with session_factory.begin() as session:
        stale = session.execute(
            select(IngestionJob.id, IngestionJob.document_id, IngestionJob.attempts)
            .where(
                IngestionJob.status == "running",
                IngestionJob.locked_at < func.now() - stale_after,
                ~worker_alive,
            )
            .with_for_update(skip_locked=True)
        ).all()
        for job_id, document_id, attempts in stale:
            if attempts >= max_attempts:
                _fail(session, job_id, document_id, "Processing was interrupted too many times.")
                continue
            session.execute(
                update(IngestionJob)
                .where(IngestionJob.id == job_id)
                .values(status="queued", locked_at=None, locked_by=None, updated_at=func.now())
            )
            _set_document(session, document_id, status="queued", error=None)
        return len(stale)


def _still_ours(job: ClaimedJob) -> ColumnElement[bool]:
    return and_(
        IngestionJob.id == job.id,
        IngestionJob.status == "running",
        IngestionJob.locked_by == job.worker_id,
        IngestionJob.locked_at == job.locked_at,
    )


def _lock_if_still_ours(session: Session, job: ClaimedJob) -> bool:
    locked = session.scalar(select(IngestionJob.id).where(_still_ours(job)).with_for_update())
    return locked is not None


def _fail(session: Session, job_id: uuid.UUID, document_id: uuid.UUID, reason: str) -> None:
    session.execute(
        update(IngestionJob)
        .where(IngestionJob.id == job_id)
        .values(
            status="failed",
            locked_at=None,
            locked_by=None,
            last_error=reason,
            updated_at=func.now(),
        )
    )
    _set_document(session, document_id, status="failed", error=reason)
    session.execute(delete(DocumentBlob).where(DocumentBlob.document_id == document_id))


def _set_document(
    session: Session, document_id: uuid.UUID, *, status: str, error: str | None
) -> None:
    session.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(status=status, error=error, updated_at=func.now())
    )

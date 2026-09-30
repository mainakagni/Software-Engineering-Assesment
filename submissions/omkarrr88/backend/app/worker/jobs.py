"""What the worker does with one job, and how each kind of failure is handled."""

import logging
import time
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.ingestion.extract import ExtractionError
from app.ingestion.pipeline import prepare_document
from app.logging_config import request_id_var
from app.providers.embeddings import Embedder
from app.providers.errors import ProviderError
from app.worker.queue import ClaimedJob, claim_next_job, complete_job, fail_job, retry_job

logger = logging.getLogger(__name__)

UNEXPECTED_FAILURE = "Processing failed unexpectedly. Delete the document and try again."


def backoff_seconds(attempt: int) -> float:
    """Wait before the next attempt: 15 s after the first failure, 60 s after the second."""
    return 15.0 * 4 ** (attempt - 1)


def provider_failure_message(error: ProviderError) -> str:
    if error.kind == "quota_exhausted":
        return (
            "The embedding service's daily quota is used up. "
            "Delete the document and upload it again tomorrow."
        )
    if error.kind == "bad_request":
        return "The embedding service rejected this document."
    return "The embedding service is not responding. Delete the document and try again later."


def process_next_job(
    session_factory: sessionmaker[Session],
    *,
    worker_id: str,
    embedder: Embedder,
    settings: Settings,
) -> bool:
    """Claims and processes one job. Returns False when the queue had nothing to run."""
    job = claim_next_job(session_factory, worker_id)
    if job is None:
        return False
    # Log lines for this job carry the request ID of the upload that created it.
    token = request_id_var.set(job.request_id)
    context: dict[str, Any] = {
        "job_id": str(job.id),
        "document_id": str(job.document_id),
        "attempt": job.attempts,
    }
    started = time.perf_counter()
    logger.info("worker.job.claimed", extra=context)
    try:
        prepared = prepare_document(session_factory, job.document_id, embedder, settings)
        stored = prepared is not None and complete_job(session_factory, job, prepared)
    except ExtractionError as exc:
        if fail_job(session_factory, job, exc.message):
            logger.info("worker.job.failed", extra={**context, "reason": exc.message})
    except ProviderError as exc:
        _retry_or_fail(
            session_factory,
            job,
            settings,
            context,
            error=str(exc),
            user_message=provider_failure_message(exc),
            retryable=exc.retryable,
        )
    except Exception as exc:
        logger.exception("worker.job.error", extra=context)
        _retry_or_fail(
            session_factory,
            job,
            settings,
            context,
            error=f"{type(exc).__name__}: {exc}",
            user_message=UNEXPECTED_FAILURE,
            retryable=True,
        )
    else:
        duration_ms = round((time.perf_counter() - started) * 1000)
        if stored and prepared is not None:
            chunk_count = len(prepared.chunks)
            logger.info(
                "worker.job.done",
                extra={**context, "chunk_count": chunk_count, "duration_ms": duration_ms},
            )
        else:
            # The document was deleted meanwhile, or the job was handed to another worker.
            logger.info("worker.job.discarded", extra={**context, "duration_ms": duration_ms})
    finally:
        request_id_var.reset(token)
    return True


def _retry_or_fail(
    session_factory: sessionmaker[Session],
    job: ClaimedJob,
    settings: Settings,
    context: dict[str, Any],
    *,
    error: str,
    user_message: str,
    retryable: bool,
) -> None:
    if retryable and job.attempts < settings.job_max_attempts:
        delay = backoff_seconds(job.attempts)
        if retry_job(session_factory, job, error, delay):
            logger.warning(
                "worker.job.retry", extra={**context, "error": error, "retry_in_seconds": delay}
            )
    elif fail_job(session_factory, job, user_message):
        logger.warning("worker.job.failed", extra={**context, "error": error})

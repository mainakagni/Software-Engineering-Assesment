"""Housekeeping the worker runs about once a minute."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.ratelimit.limiter import delete_old_windows
from app.worker.queue import requeue_stale_jobs

logger = logging.getLogger(__name__)

# Longer than the longest rate-limit window (a day), so no live counter is ever deleted.
RATE_LIMIT_RETENTION = timedelta(days=2)


def run_maintenance(session_factory: sessionmaker[Session], *, settings: Settings) -> None:
    requeued = requeue_stale_jobs(
        session_factory,
        stale_after=timedelta(minutes=settings.job_lock_timeout_minutes),
        worker_stale_after=timedelta(seconds=settings.worker_stale_after_seconds),
        max_attempts=settings.job_max_attempts,
    )
    with session_factory.begin() as session:
        deleted = delete_old_windows(session, older_than=datetime.now(UTC) - RATE_LIMIT_RETENTION)
    if requeued or deleted:
        logger.info(
            "worker.maintenance",
            extra={"stale_jobs": requeued, "rate_limit_windows_deleted": deleted},
        )

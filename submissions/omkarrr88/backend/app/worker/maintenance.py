"""Housekeeping the worker runs about once a minute. Each step runs even if another one fails."""

import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.ratelimit.limiter import delete_old_windows
from app.worker.queue import requeue_stale_jobs

logger = logging.getLogger(__name__)

# Longer than the longest rate-limit window (a day), so no live counter is ever deleted.
RATE_LIMIT_RETENTION = timedelta(days=2)


def requeue_abandoned_jobs(session_factory: sessionmaker[Session], settings: Settings) -> int:
    return requeue_stale_jobs(
        session_factory,
        stale_after=timedelta(minutes=settings.job_lock_timeout_minutes),
        worker_stale_after=timedelta(seconds=settings.worker_stale_after_seconds),
        max_attempts=settings.job_max_attempts,
    )


def delete_finished_windows(session_factory: sessionmaker[Session], _: Settings) -> int:
    with session_factory.begin() as session:
        return delete_old_windows(session, older_than=datetime.now(UTC) - RATE_LIMIT_RETENTION)


STEPS: tuple[Callable[[sessionmaker[Session], Settings], int], ...] = (
    requeue_abandoned_jobs,
    delete_finished_windows,
)


def run_maintenance(session_factory: sessionmaker[Session], *, settings: Settings) -> None:
    for step in STEPS:
        try:
            changed = step(session_factory, settings)
        except Exception:
            logger.exception("worker.maintenance_failed", extra={"step": step.__name__})
            continue
        if changed:
            logger.info("worker.maintenance", extra={"step": step.__name__, "rows": changed})

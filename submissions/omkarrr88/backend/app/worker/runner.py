"""The worker loop.

A background thread refreshes the heartbeat every few seconds (so a long job never makes the worker
look dead), while the main loop asks for the next job and sleeps when there is nothing to do.
Setting the stop event (SIGTERM/SIGINT) ends both after the current job.
"""

import logging
import threading
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.worker.heartbeat import remove_heartbeat, write_heartbeat

logger = logging.getLogger(__name__)

# Takes a session factory, processes at most one job, returns True if it did any work.
JobHandler = Callable[[sessionmaker[Session]], bool]


def no_jobs(_: sessionmaker[Session]) -> bool:
    """Placeholder handler until ingestion exists: there is never anything to do."""
    return False


def run_worker(
    session_factory: sessionmaker[Session],
    worker_id: str,
    stop: threading.Event,
    *,
    poll_interval: float,
    heartbeat_interval: float,
    handle_next_job: JobHandler = no_jobs,
) -> None:
    write_heartbeat(session_factory, worker_id)
    beat = threading.Thread(
        target=_heartbeat_loop,
        args=(session_factory, worker_id, stop, heartbeat_interval),
        name="heartbeat",
        daemon=True,
    )
    beat.start()
    logger.info("worker.started", extra={"worker_id": worker_id})

    while not stop.is_set():
        if not _handle_safely(handle_next_job, session_factory):
            stop.wait(poll_interval)  # returns early as soon as a stop is requested

    beat.join(timeout=heartbeat_interval + 1)
    try:
        remove_heartbeat(session_factory, worker_id)
    except Exception:
        logger.warning("worker.heartbeat_cleanup_failed", exc_info=True)
    logger.info("worker.stopped", extra={"worker_id": worker_id})


def _handle_safely(handle_next_job: JobHandler, session_factory: sessionmaker[Session]) -> bool:
    try:
        return handle_next_job(session_factory)
    except Exception:
        # One broken job must not kill the worker; the job handler records its own failure.
        logger.exception("worker.loop_error")
        return False


def _heartbeat_loop(
    session_factory: sessionmaker[Session], worker_id: str, stop: threading.Event, interval: float
) -> None:
    while not stop.wait(interval):
        try:
            write_heartbeat(session_factory, worker_id)
        except Exception:
            logger.warning("worker.heartbeat_failed", exc_info=True)

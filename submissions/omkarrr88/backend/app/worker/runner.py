"""The worker loop.

A background thread refreshes the heartbeat every few seconds (so a long job never makes the worker
look dead), while the main loop asks for the next job and sleeps when there is nothing to do.
Setting the stop event (SIGTERM/SIGINT) ends both after the current job.
"""

import logging
import threading
import time
from collections.abc import Callable

from sqlalchemy.orm import Session, sessionmaker

from app.worker.heartbeat import remove_heartbeat, write_heartbeat

logger = logging.getLogger(__name__)

# Takes a session factory, processes at most one job, returns True if it did any work.
JobHandler = Callable[[sessionmaker[Session]], bool]
# Housekeeping run every `maintenance_interval` seconds (e.g. requeueing stuck jobs).
Maintenance = Callable[[sessionmaker[Session]], object]


def run_worker(
    session_factory: sessionmaker[Session],
    worker_id: str,
    stop: threading.Event,
    *,
    handle_next_job: JobHandler,
    poll_interval: float,
    heartbeat_interval: float,
    maintenance: Maintenance | None = None,
    maintenance_interval: float = 60.0,
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

    next_maintenance = time.monotonic()
    while not stop.is_set():
        if maintenance is not None and time.monotonic() >= next_maintenance:
            _run_maintenance(maintenance, session_factory)
            next_maintenance = time.monotonic() + maintenance_interval
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


def _run_maintenance(maintenance: Maintenance, session_factory: sessionmaker[Session]) -> None:
    try:
        maintenance(session_factory)
    except Exception:
        logger.exception("worker.maintenance_error")


def _heartbeat_loop(
    session_factory: sessionmaker[Session], worker_id: str, stop: threading.Event, interval: float
) -> None:
    while not stop.wait(interval):
        try:
            write_heartbeat(session_factory, worker_id)
        except Exception:
            logger.warning("worker.heartbeat_failed", exc_info=True)

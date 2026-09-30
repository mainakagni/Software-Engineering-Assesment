"""Entry point: ``python -m app.worker``."""

import os
import signal
import socket
import threading
from datetime import timedelta
from functools import partial

from app.config import get_settings
from app.db.session import make_session_factory
from app.logging_config import configure_logging
from app.providers.factory import build_embedder
from app.worker.jobs import process_next_job
from app.worker.queue import requeue_stale_jobs
from app.worker.runner import run_worker


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    run_worker(
        make_session_factory(settings),
        worker_id=worker_id,
        stop=stop,
        handle_next_job=partial(
            process_next_job,
            worker_id=worker_id,
            embedder=build_embedder(settings, for_worker=True),
            settings=settings,
        ),
        poll_interval=settings.worker_poll_interval_seconds,
        heartbeat_interval=settings.worker_heartbeat_seconds,
        maintenance=partial(
            requeue_stale_jobs,
            stale_after=timedelta(minutes=settings.job_lock_timeout_minutes),
            worker_stale_after=timedelta(seconds=settings.worker_stale_after_seconds),
            max_attempts=settings.job_max_attempts,
        ),
    )


if __name__ == "__main__":
    main()

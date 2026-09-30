"""Entry point: ``python -m app.worker``."""

import os
import signal
import socket
import threading

from app.config import get_settings
from app.db.session import make_session_factory
from app.logging_config import configure_logging
from app.worker.runner import run_worker


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)

    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())

    run_worker(
        make_session_factory(settings),
        worker_id=f"{socket.gethostname()}:{os.getpid()}",
        stop=stop,
        poll_interval=settings.worker_poll_interval_seconds,
        heartbeat_interval=settings.worker_heartbeat_seconds,
    )


if __name__ == "__main__":
    main()

"""Runs the API and the ingestion worker in one container, for hosts whose free plan has no
background-worker service (Render's, for example).

    python -m app.supervisor

1. Applies the database migrations, and seeds the demo account when SEED_DEMO is set.
2. Starts the API (uvicorn) and the worker as two child processes.
3. Passes SIGTERM and SIGINT on to both. If either one exits on its own, it stops the other and
   exits with an error, so the platform restarts the container instead of leaving half of it
   running.

On a plan with background workers, run `python -m app.worker` as its own service and uvicorn on
the web service, as docker-compose.yml does; nothing else changes.
"""

import logging
import os
import signal
import subprocess
import sys
import time
from collections.abc import Sequence
from types import FrameType

from app.config import get_settings
from app.logging_config import configure_logging

logger = logging.getLogger("app.supervisor")

STOP_TIMEOUT_SECONDS = 20.0
POLL_SECONDS = 0.2
FORWARDED_SIGNALS = (signal.SIGTERM, signal.SIGINT)


def api_command(port: str) -> list[str]:
    return [
        sys.executable, "-m", "uvicorn", "app.main:create_app", "--factory",
        "--host", "0.0.0.0", "--port", port,  # noqa: S104 - the container's public port
    ]  # fmt: skip


def worker_command() -> list[str]:
    return [sys.executable, "-m", "app.worker"]


def supervise(
    commands: Sequence[Sequence[str]], *, stop_timeout: float = STOP_TIMEOUT_SECONDS
) -> int:
    """Runs the commands side by side until one exits or a stop signal arrives.

    Returns 0 after a requested stop. Otherwise it returns the exit code of the child that stopped
    first: 1 if that child exited cleanly (neither should), 128 + N if signal N killed it.
    """
    children: list[subprocess.Popen[bytes]] = []
    stop_requested = False

    def forward(signum: int, _frame: FrameType | None) -> None:
        nonlocal stop_requested
        stop_requested = True
        for child in children:
            if child.poll() is None:
                child.send_signal(signum)

    # Handlers first, so a stop that arrives while the children start is not lost.
    previous = {signum: signal.signal(signum, forward) for signum in FORWARDED_SIGNALS}
    try:
        for command in commands:
            children.append(subprocess.Popen(command))  # noqa: S603 - fixed commands
        while all(child.poll() is None for child in children):
            time.sleep(POLL_SECONDS)
        index, first = next((i, c) for i, c in enumerate(children) if c.poll() is not None)
        if not stop_requested:
            logger.error(
                "supervisor.child_exited",
                extra={"command": " ".join(commands[index]), "exit_code": first.returncode},
            )
        _stop_all(children, stop_timeout)
        if stop_requested:
            return 0
        code = first.returncode
        return 128 - code if code < 0 else (code or 1)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


def _stop_all(children: Sequence[subprocess.Popen[bytes]], timeout: float) -> None:
    for child in children:
        if child.poll() is None:
            child.terminate()
    deadline = time.monotonic() + timeout
    for child in children:
        try:
            child.wait(timeout=max(0.1, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    # A failed migration stops the start: the platform retries, and nothing runs on an old schema.
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    if settings.seed_demo:
        # The demo account is a convenience: the app still starts if seeding fails.
        seeded = subprocess.run([sys.executable, "-m", "app.seed"], check=False)
        if seeded.returncode != 0:
            logger.error("supervisor.seed_failed", extra={"exit_code": seeded.returncode})
    port = os.environ.get("PORT", "8000")
    logger.info("supervisor.starting", extra={"port": port})
    return supervise([api_command(port), worker_command()])


if __name__ == "__main__":
    sys.exit(main())

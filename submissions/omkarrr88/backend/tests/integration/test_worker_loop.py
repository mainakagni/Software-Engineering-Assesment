import threading
import time

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import WorkerHeartbeat
from app.worker.runner import run_worker


def _heartbeat_times(db: sessionmaker[Session]) -> list:
    with db() as session:
        return list(session.scalars(select(WorkerHeartbeat.last_seen_at)))


def _run_in_thread(db: sessionmaker[Session], stop: threading.Event, **kwargs) -> threading.Thread:
    worker = threading.Thread(
        target=run_worker,
        args=(db, "test-worker", stop),
        kwargs={"poll_interval": 0.01, "heartbeat_interval": 0.05, **kwargs},
    )
    worker.start()
    return worker


def _wait_until(condition, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.01)
    return False


def test_heartbeat_is_written_at_start_and_removed_at_stop(db: sessionmaker[Session]) -> None:
    stop = threading.Event()
    worker = _run_in_thread(db, stop)
    assert _wait_until(lambda: len(_heartbeat_times(db)) == 1)

    stop.set()
    worker.join(timeout=3)
    assert not worker.is_alive()
    assert _heartbeat_times(db) == []


def test_heartbeat_keeps_being_refreshed(db: sessionmaker[Session]) -> None:
    stop = threading.Event()
    worker = _run_in_thread(db, stop)
    assert _wait_until(lambda: len(_heartbeat_times(db)) == 1)
    first = _heartbeat_times(db)[0]
    assert _wait_until(lambda: _heartbeat_times(db)[0] > first)
    stop.set()
    worker.join(timeout=3)


def test_a_failing_job_handler_does_not_stop_the_worker(db: sessionmaker[Session]) -> None:
    calls: list[int] = []

    def flaky_handler(_: sessionmaker[Session]) -> bool:
        calls.append(1)
        raise RuntimeError("job exploded")

    stop = threading.Event()
    worker = _run_in_thread(db, stop, handle_next_job=flaky_handler)
    assert _wait_until(lambda: len(calls) >= 3)
    assert worker.is_alive()
    stop.set()
    worker.join(timeout=3)
    assert not worker.is_alive()

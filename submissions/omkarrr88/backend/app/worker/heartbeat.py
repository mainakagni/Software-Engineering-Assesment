import socket

from sqlalchemy import delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import WorkerHeartbeat


def write_heartbeat(session_factory: sessionmaker[Session], worker_id: str) -> None:
    """Insert or refresh this worker's row; /health reads the newest last_seen_at."""
    stmt = insert(WorkerHeartbeat).values(
        worker_id=worker_id,
        hostname=socket.gethostname(),
        started_at=func.now(),
        last_seen_at=func.now(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=[WorkerHeartbeat.worker_id], set_={"last_seen_at": func.now()}
    )
    with session_factory.begin() as session:
        session.execute(stmt)


def remove_heartbeat(session_factory: sessionmaker[Session], worker_id: str) -> None:
    with session_factory.begin() as session:
        session.execute(delete(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == worker_id))

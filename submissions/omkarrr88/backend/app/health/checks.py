"""Dependency checks for /health. Each one is independent, never raises, and never reports
internal error text (that goes to the logs)."""

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

Status = Literal["ok", "down"]


@dataclass(frozen=True)
class CheckResult:
    status: Status
    details: dict[str, Any] = field(default_factory=dict)


def check_database(session: Session) -> CheckResult:
    session.execute(text("SELECT 1"))
    return CheckResult("ok")


def check_vector_store(session: Session) -> CheckResult:
    version = session.execute(
        text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
    ).scalar()
    if version is None:
        return CheckResult("down", {"reason": "pgvector extension is not installed"})
    # A real distance computation, not just the catalog entry.
    session.execute(text("SELECT '[1,0]'::vector <=> '[0,1]'::vector"))
    return CheckResult("ok", {"pgvector_version": version})


def check_queue(session: Session) -> CheckResult:
    queued, oldest_age = session.execute(
        text(
            "SELECT count(*), EXTRACT(EPOCH FROM now() - min(created_at)) "
            "FROM ingestion_jobs WHERE status = 'queued'"
        )
    ).one()
    details: dict[str, Any] = {"queued_jobs": queued}
    if oldest_age is not None:
        details["oldest_queued_seconds"] = round(float(oldest_age))
    return CheckResult("ok", details)


def check_worker(session: Session, stale_after_seconds: float) -> CheckResult:
    age = session.execute(
        text("SELECT EXTRACT(EPOCH FROM now() - max(last_seen_at)) FROM worker_heartbeats")
    ).scalar()
    if age is None:
        return CheckResult("down", {"reason": "no running worker"})
    details = {"last_heartbeat_seconds_ago": round(float(age))}
    return CheckResult("ok" if age <= stale_after_seconds else "down", details)


def run_check(
    name: str, session_factory: sessionmaker[Session], check: Callable[[Session], CheckResult]
) -> CheckResult:
    """Runs one check in its own short session so a failure cannot affect the others."""
    try:
        with session_factory() as session:
            return check(session)
    except Exception:
        logger.warning("health.check_failed", extra={"check": name}, exc_info=True)
        return CheckResult("down", {"reason": "unreachable"})

"""Fixed-window rate limits stored in Postgres, so they hold across processes and restarts.

A fixed window allows up to twice the limit in a burst around a window boundary. That is accepted
here: the global daily cap bounds the total, and the counting is one atomic upsert.
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import RateLimitCounter


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    count: int
    limit: int
    retry_after_seconds: int


def window_start(now: datetime, window_seconds: int) -> datetime:
    """The start of the fixed window that contains `now` (windows are aligned to the epoch)."""
    epoch_seconds = int(now.timestamp())
    return datetime.fromtimestamp(epoch_seconds - epoch_seconds % window_seconds, UTC)


def hit(
    session: Session, key: str, *, limit: int, window_seconds: int, now: datetime
) -> RateLimitDecision:
    """Counts one event for `key` and says whether it is within the limit."""
    start = window_start(now, window_seconds)
    statement = (
        insert(RateLimitCounter)
        .values(key=key, window_start=start, count=1)
        .on_conflict_do_update(
            index_elements=[RateLimitCounter.key, RateLimitCounter.window_start],
            set_={"count": RateLimitCounter.count + 1},
        )
        .returning(RateLimitCounter.count)
    )
    count = session.execute(statement).scalar_one()
    window_end = start + timedelta(seconds=window_seconds)
    retry_after = max(1, math.ceil((window_end - now).total_seconds()))
    return RateLimitDecision(
        allowed=count <= limit, count=count, limit=limit, retry_after_seconds=retry_after
    )


def describe_wait(seconds: int) -> str:
    """How long to wait, in the unit a person would use: '40 seconds', '12 minutes', '5 hours'."""
    for unit, size in (("hour", 3600), ("minute", 60)):
        if seconds >= 2 * size:
            count = round(seconds / size)
            return f"{count} {unit}s"
    return f"{seconds} second" + ("" if seconds == 1 else "s")


def delete_old_windows(session: Session, *, older_than: datetime) -> int:
    """Removes counters of windows that started before `older_than`; returns how many."""
    deleted = session.scalars(
        delete(RateLimitCounter)
        .where(RateLimitCounter.window_start < older_than)
        .returning(RateLimitCounter.key)
    ).all()
    return len(deleted)

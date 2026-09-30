"""A shared budget for the passages the worker embeds, so uploads cannot use up the day's quota.

Gemini's free tier allows 1,000 embedding requests a day for the whole deployment: one for each
passage of an uploaded document and one for each new question. Documents may use
GLOBAL_PASSAGES_PER_DAY of them in any 24 hours, and the rest is left for questions, which have
their own daily cap.

The count lives in the rate-limit counters table, in hourly buckets, and covers the current hour and
the 23 before it. A rolling window holds whenever the provider's day starts (midnight Pacific
time); a fixed UTC day would let two days' budgets land inside one of Gemini's days.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db.models import RateLimitCounter
from app.ratelimit.limiter import window_start

KEY = "embed:passages"
BUCKET = timedelta(hours=1)
WINDOW = 24 * BUCKET
# Any fixed number works: every worker takes the same advisory lock before counting.
LOCK_ID = 7_300_024


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    left: int  # passages still free in the last 24 hours, after this request if it was allowed
    retry_after_seconds: int = 0  # if refused: until enough counted passages leave the window


def spend_passages(
    session: Session, passages: int, *, budget: int, now: datetime
) -> BudgetDecision:
    """Counts `passages` against the budget if the last 24 hours leave room for all of them.

    A request that does not fit is not counted at all. Must run inside the caller's transaction.
    """
    # One request at a time, so two workers cannot both take the last passages.
    session.execute(select(func.pg_advisory_xact_lock(LOCK_ID)))
    bucket = window_start(now, int(BUCKET.total_seconds()))
    since = bucket - WINDOW  # the window is the buckets after this one, up to the current one
    used = int(
        session.scalar(
            select(func.coalesce(func.sum(RateLimitCounter.count), 0)).where(
                RateLimitCounter.key == KEY, RateLimitCounter.window_start > since
            )
        )
        or 0
    )
    left = max(0, budget - used)
    if passages > left:
        wait = _seconds_until_room(session, since, passages + used - budget, now)
        return BudgetDecision(allowed=False, left=left, retry_after_seconds=wait)
    session.execute(
        insert(RateLimitCounter)
        .values(key=KEY, window_start=bucket, count=passages)
        .on_conflict_do_update(
            index_elements=[RateLimitCounter.key, RateLimitCounter.window_start],
            set_={"count": RateLimitCounter.count + passages},
        )
    )
    return BudgetDecision(allowed=True, left=left - passages)


def _seconds_until_room(session: Session, since: datetime, needed: int, now: datetime) -> int:
    """How long until the oldest counted passages leave the window and free `needed` of them.

    A bucket leaves the window 24 hours after it started.
    """
    freed = 0
    buckets = session.execute(
        select(RateLimitCounter.window_start, RateLimitCounter.count)
        .where(RateLimitCounter.key == KEY, RateLimitCounter.window_start > since)
        .order_by(RateLimitCounter.window_start)
    )
    for started, count in buckets:
        freed += count
        if freed >= needed:
            return max(1, math.ceil((started + WINDOW - now).total_seconds()))
    return int(WINDOW.total_seconds())  # more than the whole budget was asked for

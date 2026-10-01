"""The rolling budget of embedded passages that keeps uploads from using the questions' quota."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session, sessionmaker

from app.ratelimit.budget import BudgetDecision, spend_passages

NOW = datetime(2026, 10, 1, 12, 30, tzinfo=UTC)


def _spend(
    db: sessionmaker[Session], passages: int, *, budget: int = 100, now: datetime = NOW
) -> BudgetDecision:
    with db.begin() as session:
        return spend_passages(session, passages, budget=budget, now=now)


def test_passages_are_counted_until_the_budget_is_used(db: sessionmaker[Session]) -> None:
    assert _spend(db, 60) == BudgetDecision(allowed=True, left=40)
    assert _spend(db, 40) == BudgetDecision(allowed=True, left=0)  # exactly the budget
    refused = _spend(db, 1)
    assert (refused.allowed, refused.left) == (False, 0)


def test_a_refused_request_uses_none_of_the_budget(db: sessionmaker[Session]) -> None:
    assert _spend(db, 70).allowed
    refused = _spend(db, 50)
    assert (refused.allowed, refused.left) == (False, 30)
    assert _spend(db, 30).allowed  # the 50 that did not fit were not counted


def test_the_budget_covers_the_last_24_hours(db: sessionmaker[Session]) -> None:
    assert _spend(db, 100, now=NOW - timedelta(hours=23)).allowed
    assert not _spend(db, 1).allowed  # 23 hours later those passages still count
    assert _spend(db, 100, now=NOW + timedelta(hours=1)).allowed  # a day later they do not


def test_a_refusal_says_when_there_will_be_room(db: sessionmaker[Session]) -> None:
    _spend(db, 60, now=NOW - timedelta(hours=20))  # counted in the 16:00 bucket of the day before
    _spend(db, 40, now=NOW - timedelta(hours=2))  # counted in the 10:00 bucket
    # 50 fit once the first 60 leave the window at 16:00, three and a half hours from now.
    assert _spend(db, 50).retry_after_seconds == 12_600
    # 70 also need the 40 to leave, at 10:00 tomorrow.
    assert _spend(db, 70).retry_after_seconds == 77_400


def test_any_24_hours_stay_within_the_budget(db: sessionmaker[Session]) -> None:
    # Spend a little every hour for two days. Gemini's day starts at midnight Pacific time, not at
    # midnight UTC, so no 24 consecutive hours may add up to more than the budget.
    spent: dict[datetime, int] = {}
    for hour in range(48):
        now = NOW + timedelta(hours=hour)
        if _spend(db, 30, now=now).allowed:
            spent[now] = 30
    for start in range(25):
        window_start = NOW + timedelta(hours=start)
        window_end = window_start + timedelta(hours=24)
        assert sum(n for at, n in spent.items() if window_start <= at < window_end) <= 100

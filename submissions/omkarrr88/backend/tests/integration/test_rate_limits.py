"""Rate limits on questions, uploads and credentials, and the clean-up of old counters."""

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import RateLimitCounter
from app.ratelimit.limiter import delete_old_windows, hit
from app.worker.maintenance import run_maintenance
from tests.conftest import ClientFactory, make_test_settings, signup

NOW = datetime(2026, 9, 30, 12, 0, 30, tzinfo=UTC)


def _post(
    client: TestClient, headers: dict[str, str] | None, question: str = "Why?", **body: Any
) -> Response:
    return client.post("/api/questions", headers=headers, json={"question": question, **body})


# --- counting ------------------------------------------------------------------------------------


def test_counting_within_and_across_windows(db: sessionmaker[Session]) -> None:
    with db.begin() as session:
        first = hit(session, "k", limit=2, window_seconds=60, now=NOW)
        second = hit(session, "k", limit=2, window_seconds=60, now=NOW + timedelta(seconds=5))
        third = hit(session, "k", limit=2, window_seconds=60, now=NOW + timedelta(seconds=10))
        next_window = hit(session, "k", limit=2, window_seconds=60, now=NOW + timedelta(seconds=40))
    assert [d.allowed for d in (first, second, third)] == [True, True, False]
    assert (third.count, third.retry_after_seconds) == (3, 20)
    assert (next_window.allowed, next_window.count) == (True, 1)


def test_old_windows_are_cleaned_up(db: sessionmaker[Session]) -> None:
    with db.begin() as session:
        hit(session, "old", limit=5, window_seconds=60, now=NOW - timedelta(days=3))
        hit(session, "new", limit=5, window_seconds=60, now=NOW)
        assert delete_old_windows(session, older_than=NOW - timedelta(days=2)) == 1
        assert session.scalars(select(RateLimitCounter.key)).all() == ["new"]


def test_maintenance_deletes_counters_of_finished_windows(db: sessionmaker[Session]) -> None:
    now = datetime.now(UTC)
    with db.begin() as session:
        hit(session, "yesterday", limit=5, window_seconds=86_400, now=now - timedelta(days=1))
        hit(session, "last-week", limit=5, window_seconds=60, now=now - timedelta(days=7))
    run_maintenance(db, settings=make_test_settings())
    with db() as session:
        assert session.scalars(select(RateLimitCounter.key)).all() == ["yesterday"]


# --- question limits -----------------------------------------------------------------------------


def test_questions_per_minute(client_factory: ClientFactory) -> None:
    client = client_factory(questions_per_minute=2)
    headers = signup(client)
    assert [_post(client, headers).status_code for _ in range(2)] == [200, 200]

    response = _post(client, headers)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"
    assert 1 <= int(response.headers["Retry-After"]) <= 60
    assert _post(client, signup(client, "bob@example.com")).status_code == 200  # others unaffected


def test_questions_per_day(client_factory: ClientFactory) -> None:
    client = client_factory(questions_per_day=1)
    headers = signup(client)
    assert _post(client, headers).status_code == 200
    response = _post(client, headers)
    assert response.status_code == 429
    assert "today's limit of 1 questions" in response.json()["error"]["message"]


def test_global_daily_cap(client_factory: ClientFactory) -> None:
    client = client_factory(global_questions_per_day=2)
    for email in ("a@example.com", "b@example.com"):
        assert _post(client, signup(client, email)).status_code == 200
    response = _post(client, signup(client, "c@example.com"))
    assert response.status_code == 429
    assert "question limit for today" in response.json()["error"]["message"]


def test_a_blocked_user_does_not_use_up_the_global_cap(client_factory: ClientFactory) -> None:
    client = client_factory(questions_per_minute=1, global_questions_per_day=3)
    spammer = signup(client, "spam@example.com")
    statuses = [_post(client, spammer).status_code for _ in range(10)]
    assert statuses == [200] + [429] * 9
    assert _post(client, signup(client, "bob@example.com")).status_code == 200


def test_requests_without_a_token_are_not_counted(client_factory: ClientFactory) -> None:
    client = client_factory(global_questions_per_day=1)
    assert [_post(client, None).status_code for _ in range(3)] == [401, 401, 401]
    assert _post(client, signup(client)).status_code == 200


# --- upload limits -------------------------------------------------------------------------------


def _upload(client: TestClient, headers: dict[str, str], name: str) -> int:
    files = {"file": (name, f"Notes kept in {name}.".encode(), "text/plain")}
    return client.post("/api/documents", headers=headers, files=files).status_code


def test_uploads_per_day(client_factory: ClientFactory) -> None:
    client = client_factory(uploads_per_day=2)
    headers = signup(client)
    assert [_upload(client, headers, f"note-{i}.txt") for i in range(3)] == [202, 202, 429]
    assert _upload(client, signup(client, "bob@example.com"), "bob.txt") == 202


def test_global_upload_cap(client_factory: ClientFactory) -> None:
    client = client_factory(global_uploads_per_day=1)
    assert _upload(client, signup(client, "alice@example.com"), "a.txt") == 202
    response = client.post(
        "/api/documents",
        headers=signup(client, "bob@example.com"),
        files={"file": ("b.txt", b"Bob's notes.", "text/plain")},
    )
    assert response.status_code == 429
    assert "upload limit for today" in response.json()["error"]["message"]


# --- credential limits ---------------------------------------------------------------------------


def test_login_attempts_are_limited_per_ip(client_factory: ClientFactory) -> None:
    client = client_factory(auth_attempts_per_minute=3)
    signup(client)  # the first attempt
    bad = {"email": "alice@example.com", "password": "wrong password"}
    assert [client.post("/api/auth/login", json=bad).status_code for _ in range(3)] == [
        401,
        401,
        429,
    ]
    form = {"username": "alice@example.com", "password": "correct horse battery"}
    assert client.post("/api/auth/token", data=form).status_code == 429


def test_behind_a_proxy_each_client_ip_has_its_own_limit(client_factory: ClientFactory) -> None:
    client = client_factory(auth_attempts_per_minute=1, trust_proxy_headers=True)
    bad = {"email": "a@example.com", "password": "wrong password"}

    def login(ip: str) -> int:
        # The client may send its own X-Forwarded-For; the proxy appends the address it saw.
        headers = {"X-Forwarded-For": f"6.6.6.6, {ip}"}
        return client.post("/api/auth/login", json=bad, headers=headers).status_code

    assert [login("203.0.113.1"), login("203.0.113.1"), login("203.0.113.2")] == [401, 429, 401]

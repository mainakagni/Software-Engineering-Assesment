import json
import logging
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.tokens import create_access_token
from app.config import Settings
from app.db.models import User
from app.logging_config import JsonFormatter
from tests.conftest import signup

PASSWORD = "correct horse battery"


def test_signup_returns_a_working_token(client: TestClient) -> None:
    response = client.post(
        "/api/auth/signup", json={"email": " Alice@Example.com ", "password": PASSWORD}
    )
    body = response.json()["data"]
    assert response.status_code == 201
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert body["user"]["email"] == "alice@example.com"

    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["data"]["id"] == body["user"]["id"]


def test_password_is_stored_hashed(client: TestClient, db: sessionmaker[Session]) -> None:
    signup(client)
    with db() as session:
        stored = session.scalar(select(User.password_hash))
    assert stored is not None
    assert stored.startswith("$argon2id$")
    assert PASSWORD not in stored


def test_the_same_email_cannot_sign_up_twice(client: TestClient) -> None:
    signup(client, "alice@example.com")
    response = client.post(
        "/api/auth/signup", json={"email": "ALICE@example.com", "password": PASSWORD}
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"email": "not-an-email", "password": PASSWORD}, "email"),
        ({"email": "alice@example.com", "password": "short"}, "password"),
        ({"email": "alice@example.com", "password": "x" * 129}, "password"),
        ({"email": "alice@example.com"}, "password"),
    ],
)
def test_signup_validates_its_input(client: TestClient, payload: dict, field: str) -> None:
    response = client.post("/api/auth/signup", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["details"][0]["field"] == field


def test_login_with_the_right_password(client: TestClient) -> None:
    signup(client)
    response = client.post(
        "/api/auth/login", json={"email": "ALICE@example.com", "password": PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["data"]["user"]["email"] == "alice@example.com"


@pytest.mark.parametrize(
    "credentials",
    [
        {"email": "alice@example.com", "password": "wrong password"},
        {"email": "nobody@example.com", "password": PASSWORD},
        {"email": "not even an email", "password": PASSWORD},
    ],
    ids=["wrong-password", "unknown-email", "malformed-email"],
)
def test_failed_logins_all_look_the_same(client: TestClient, credentials: dict) -> None:
    signup(client)
    response = client.post("/api/auth/login", json=credentials)
    assert response.status_code == 401
    assert response.json()["error"]["message"] == "Invalid email or password."


def test_swagger_token_endpoint_uses_the_oauth2_form(client: TestClient) -> None:
    signup(client)
    response = client.post(
        "/api/auth/token", data={"username": "alice@example.com", "password": PASSWORD}
    )
    body = response.json()
    assert response.status_code == 200
    assert body["token_type"] == "bearer"
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200


def test_me_requires_a_token(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.json()["error"]["code"] == "unauthorized"


@pytest.mark.parametrize("header", ["Bearer nonsense", "Basic YWxpY2U6cGFzcw==", "Bearer "])
def test_me_rejects_bad_authorization_headers(client: TestClient, header: str) -> None:
    response = client.get("/api/auth/me", headers={"Authorization": header})
    assert response.status_code == 401


def test_expired_token_is_rejected(client: TestClient, settings: Settings) -> None:
    headers = signup(client)
    user_id = uuid.UUID(client.get("/api/auth/me", headers=headers).json()["data"]["id"])
    old, _ = create_access_token(user_id, settings, now=datetime.now(UTC) - timedelta(days=1))
    response = client.get("/api/auth/me", headers={"Authorization": f"Bearer {old}"})
    assert response.status_code == 401


def test_token_of_a_deleted_account_stops_working(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    headers = signup(client)
    with db.begin() as session:
        session.execute(delete(User))
    assert client.get("/api/auth/me", headers=headers).status_code == 401


class _JsonLines(logging.Handler):
    """Formats each record when it is emitted, i.e. inside the request, like the real handler."""

    def __init__(self) -> None:
        super().__init__()
        self.lines: list[dict] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(json.loads(JsonFormatter().format(record)))


def test_access_log_line_names_the_user(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    headers = signup(client)
    user_id = client.get("/api/auth/me", headers=headers).json()["data"]["id"]
    capture = _JsonLines()
    http_logger = logging.getLogger("app.http")
    http_logger.addHandler(capture)
    try:
        with caplog.at_level(logging.INFO, logger="app.http"):
            client.get("/api/auth/me", headers=headers)
    finally:
        http_logger.removeHandler(capture)
    assert capture.lines[-1]["user_id"] == user_id

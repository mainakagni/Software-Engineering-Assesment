"""Middleware and error envelopes, tested on a small app with no database."""

import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from app.errors import (
    NotFoundError,
    RateLimitedError,
    UnauthorizedError,
    register_error_handlers,
)
from app.middleware import (
    CSP_APP,
    CSP_DOCS,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    resolve_request_id,
)


class Item(BaseModel):
    name: str
    count: int


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    @app.get("/ok")
    def ok_route() -> dict[str, str]:
        return {"hello": "world"}

    @app.post("/items")
    def create_item(item: Item) -> Item:
        return item

    @app.get("/missing")
    def missing() -> None:
        raise NotFoundError("That item does not exist.")

    @app.get("/limited")
    def limited() -> None:
        raise RateLimitedError("Slow down.", retry_after_seconds=42)

    @app.get("/private")
    def private() -> None:
        raise UnauthorizedError()

    @app.get("/boom")
    def boom() -> None:
        raise RuntimeError("database password is hunter2")

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_app(), raise_server_exceptions=False)


def test_request_id_is_generated_and_returned(client: TestClient) -> None:
    response = client.get("/ok")
    assert len(response.headers["X-Request-ID"]) == 32


def test_valid_incoming_request_id_is_kept(client: TestClient) -> None:
    response = client.get("/ok", headers={"X-Request-ID": "trace-abc.123"})
    assert response.headers["X-Request-ID"] == "trace-abc.123"


@pytest.mark.parametrize("bad", ["", "has spaces", "a" * 65, "semi;colon", "<script>"])
def test_unsafe_request_ids_are_replaced(bad: str) -> None:
    assert resolve_request_id(bad) != bad


def test_access_log_line_per_request(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="app.http"):
        client.get("/ok")
    record = next(r for r in caplog.records if r.getMessage() == "http.request")
    assert (record.method, record.path, record.status) == ("GET", "/ok", 200)  # type: ignore[attr-defined]


def test_liveness_probes_are_logged_at_debug(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG, logger="app.http"):
        client.get("/health/live")
    record = next(r for r in caplog.records if r.getMessage() == "http.request")
    assert record.levelno == logging.DEBUG


def test_security_headers(client: TestClient) -> None:
    headers = client.get("/ok").headers
    assert headers["Content-Security-Policy"] == CSP_APP
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["X-Frame-Options"] == "DENY"
    assert "Strict-Transport-Security" not in headers


def test_docs_pages_get_the_relaxed_policy(client: TestClient) -> None:
    assert client.get("/docs").headers["Content-Security-Policy"] == CSP_DOCS
    assert client.get("/redoc").headers["Content-Security-Policy"] == CSP_DOCS


@pytest.mark.parametrize("path", ["/docs-evil", "/docsx", "/redoc/../x", "/documents"])
def test_lookalike_paths_keep_the_strict_policy(client: TestClient, path: str) -> None:
    assert client.get(path).headers["Content-Security-Policy"] == CSP_APP


def test_unknown_route_uses_the_error_envelope(client: TestClient) -> None:
    response = client.get("/nope")
    body = response.json()
    assert response.status_code == 404
    assert body["success"] is False
    assert body["error"]["code"] == "not_found"
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]


def test_wrong_method_is_405(client: TestClient) -> None:
    response = client.delete("/ok")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


def test_validation_errors_list_the_fields(client: TestClient) -> None:
    response = client.post("/items", json={"name": "x", "count": "many"})
    body = response.json()
    assert response.status_code == 422
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["details"][0]["field"] == "count"


def test_app_errors_keep_their_status_code_and_message(client: TestClient) -> None:
    response = client.get("/missing")
    assert response.status_code == 404
    assert response.json()["error"]["message"] == "That item does not exist."


def test_rate_limited_sets_retry_after(client: TestClient) -> None:
    response = client.get("/limited")
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "42"


def test_unauthorized_sets_www_authenticate(client: TestClient) -> None:
    response = client.get("/private")
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"


def test_unexpected_errors_do_not_leak_details(client: TestClient) -> None:
    response = client.get("/boom")
    body = response.json()
    assert response.status_code == 500
    assert body["error"]["code"] == "internal_error"
    assert "hunter2" not in response.text
    assert body["error"]["request_id"] == response.headers["X-Request-ID"]

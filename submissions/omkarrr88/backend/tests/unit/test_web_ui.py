"""Serving the built web UI next to the API."""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.main import create_app
from app.web import mount_web_ui
from tests.conftest import make_test_settings

INDEX = "<!doctype html><title>DocuMind</title>"


@pytest.fixture
def build(tmp_path: Path) -> Path:
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text(INDEX)
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path / "assets" / "index-abc123.js").write_text("console.log(1)")
    (tmp_path.parent / "secret.txt").write_text("outside the build")
    return tmp_path


@pytest.fixture
def client(build: Path) -> TestClient:
    return TestClient(create_app(make_test_settings(static_dir=str(build))))


def test_index_and_client_side_routes_get_the_page(client: TestClient) -> None:
    for path in ("/", "/documents", "/some/deep/link"):
        response = client.get(path)
        assert response.status_code == 200
        assert response.text == INDEX
        assert response.headers["cache-control"] == "no-cache"
        assert "script-src 'self'" in response.headers["content-security-policy"]


def test_hashed_assets_are_cached_for_long(client: TestClient) -> None:
    response = client.get("/assets/index-abc123.js")
    assert response.status_code == 200
    assert "immutable" in response.headers["cache-control"]
    assert client.get("/assets/missing.js").status_code == 404


def test_files_at_the_root_are_served(client: TestClient) -> None:
    response = client.get("/favicon.svg")
    assert (response.status_code, response.text) == (200, "<svg/>")


@pytest.mark.parametrize("path", ["/api/nothing-here", "/api", "/health/nope", "/docs/extra"])
def test_unknown_api_paths_stay_json_404s(client: TestClient, path: str) -> None:
    response = client.get(path)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_files_outside_the_build_are_not_served(client: TestClient) -> None:
    for path in ("/../secret.txt", "/%2e%2e/secret.txt", "/assets/../../secret.txt"):
        response = client.get(path)
        assert "outside the build" not in response.text


def test_the_api_still_answers_first(client: TestClient) -> None:
    assert client.get("/health/live").json()["data"]["status"] == "ok"
    assert client.get("/openapi.json").status_code == 200


def test_without_a_build_nothing_is_mounted(tmp_path: Path) -> None:
    app = FastAPI()
    assert mount_web_ui(app, tmp_path / "missing") is False
    assert TestClient(app).get("/").status_code == 404

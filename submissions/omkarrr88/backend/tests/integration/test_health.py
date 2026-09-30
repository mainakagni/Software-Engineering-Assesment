from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import insert
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import WorkerHeartbeat
from app.db.session import make_session_factory
from app.main import create_app
from tests.conftest import make_test_settings


def _heartbeat(db: sessionmaker[Session], age_seconds: float) -> None:
    seen = datetime.now(UTC) - timedelta(seconds=age_seconds)
    with db.begin() as session:
        session.execute(
            insert(WorkerHeartbeat).values(
                worker_id="w1", hostname="h", started_at=seen, last_seen_at=seen
            )
        )


def test_liveness_does_not_need_the_database() -> None:
    settings = make_test_settings(database_url="postgresql+psycopg://x:y@127.0.0.1:1/none")
    with TestClient(create_app(settings)) as client:
        response = client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["data"] == {"status": "ok"}


def test_healthy_when_everything_works(client: TestClient, db: sessionmaker[Session]) -> None:
    _heartbeat(db, age_seconds=1)
    response = client.get("/health")
    body = response.json()["data"]
    assert response.status_code == 200
    assert body["status"] == "ok"
    assert {name: check["status"] for name, check in body["checks"].items()} == {
        "database": "ok",
        "vector_store": "ok",
        "queue": "ok",
        "worker": "ok",
    }
    assert body["checks"]["vector_store"]["details"]["pgvector_version"]
    assert body["checks"]["queue"]["details"]["queued_jobs"] == 0


def test_degraded_without_a_worker_heartbeat(client: TestClient) -> None:
    response = client.get("/health")
    body = response.json()["data"]
    assert response.status_code == 503
    assert body["status"] == "degraded"
    assert body["checks"]["worker"]["status"] == "down"
    assert body["checks"]["database"]["status"] == "ok"


def test_stale_heartbeat_counts_as_down(client: TestClient, db: sessionmaker[Session]) -> None:
    _heartbeat(db, age_seconds=600)
    worker = client.get("/health").json()["data"]["checks"]["worker"]
    assert worker["status"] == "down"
    assert worker["details"]["last_heartbeat_seconds_ago"] >= 600


def test_unreachable_database_reports_down_without_leaking_errors() -> None:
    settings = make_test_settings(database_url="postgresql+psycopg://x:y@127.0.0.1:1/none")
    app = create_app(settings)
    app.state.session_factory = make_session_factory(settings)
    with TestClient(app) as client:
        response = client.get("/health")
    checks = response.json()["data"]["checks"]
    assert response.status_code == 503
    assert all(check["status"] == "down" for check in checks.values())
    assert checks["database"]["details"] == {"reason": "unreachable"}
    assert "127.0.0.1" not in response.text

"""The demo account: created once, and its sample documents queued again when they go missing."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import seed
from app.config import Settings
from app.db.models import Document, IngestionJob, User
from app.main import create_app
from app.seed import sample_files, seed_demo
from app.worker.jobs import process_next_job
from tests.conftest import make_test_settings

PASSWORD = "a demo password"


@pytest.fixture
def demo_settings(settings: Settings) -> Settings:
    return settings.model_copy(
        update={"demo_user_email": " Demo@Example.com ", "demo_user_password": SecretStr(PASSWORD)}
    )


@pytest.fixture
def samples(tmp_path: Path) -> list[Path]:
    (tmp_path / "leave.md").write_text("# Leave\nEmployees get 25 paid days off each year.\n")
    (tmp_path / "travel.txt").write_text("Flights must be booked 14 business days ahead.\n")
    return sorted(tmp_path.iterdir())


def _documents(db: sessionmaker[Session]) -> list[str]:
    with db() as session:
        return sorted(session.scalars(select(Document.filename)))


def test_seeding_twice_creates_one_account_and_queues_each_sample_once(
    db: sessionmaker[Session], demo_settings: Settings, samples: list[Path]
) -> None:
    assert seed_demo(db, demo_settings, samples) == 2
    assert seed_demo(db, demo_settings, samples) == 0

    with db() as session:
        assert session.scalars(select(User.email)).all() == ["demo@example.com"]
        assert session.scalar(select(func.count()).select_from(IngestionJob)) == 2
    assert _documents(db) == ["leave.md", "travel.txt"]


def test_a_deleted_sample_comes_back(
    db: sessionmaker[Session], demo_settings: Settings, samples: list[Path]
) -> None:
    seed_demo(db, demo_settings, samples)
    with db.begin() as session:
        session.execute(delete(Document).where(Document.filename == "leave.md"))

    assert seed_demo(db, demo_settings, samples) == 1
    assert _documents(db) == ["leave.md", "travel.txt"]


def test_the_demo_account_can_log_in_and_sees_its_processed_samples(
    db: sessionmaker[Session], demo_settings: Settings, samples: list[Path]
) -> None:
    seed_demo(db, demo_settings, samples)
    app = create_app(make_test_settings())
    with TestClient(app) as client:
        state = client.app.state  # type: ignore[attr-defined]
        while process_next_job(db, worker_id="t", embedder=state.embedder, settings=state.settings):
            pass
        login = client.post(
            "/api/auth/login", json={"email": "demo@example.com", "password": PASSWORD}
        )
        assert login.status_code == 200, login.text
        token = login.json()["data"]["access_token"]
        listed = client.get("/api/documents", headers={"Authorization": f"Bearer {token}"})
    assert {d["status"] for d in listed.json()["data"]} == {"ready"}


def test_seeding_needs_the_account_details(db: sessionmaker[Session], settings: Settings) -> None:
    with pytest.raises(ValueError, match="DEMO_USER_EMAIL"):
        seed_demo(db, settings, [])


def test_main_reports_failure_without_raising(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed, "get_settings", lambda: make_test_settings())
    assert seed.main() == 1  # no demo account configured


def test_the_samples_are_the_evaluation_corpus() -> None:
    names = [path.name for path in sample_files()]
    assert "ATTRIBUTION.md" not in names
    assert {"gitlab-time-off.md", "nist-csf-2.0.pdf"} <= set(names)

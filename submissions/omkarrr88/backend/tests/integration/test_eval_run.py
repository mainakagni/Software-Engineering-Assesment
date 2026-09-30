"""The evaluation harness end to end, with the offline embedder and model."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Document
from evaluation import report, run
from evaluation.dataset import corpus_files
from tests.conftest import TEST_DATABASE_URL


@pytest.fixture
def offline_env(monkeypatch: pytest.MonkeyPatch, db: sessionmaker[Session]) -> Iterator[None]:
    for name, value in {
        "DATABASE_URL": TEST_DATABASE_URL,
        "EVAL_DATABASE_URL": TEST_DATABASE_URL,
        "LLM_PROVIDER": "fake",
        "EMBEDDING_PROVIDER": "fake",
        "APP_ENV": "test",
        "LOG_LEVEL": "WARNING",
    }.items():
        monkeypatch.setenv(name, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.usefixtures("offline_env")
def test_a_run_ingests_the_corpus_once_and_scores_every_question(
    tmp_path: Path, db: sessionmaker[Session], capsys: pytest.CaptureFixture[str]
) -> None:
    arguments = ["--split", "dev", "--pause", "0", "--out-dir", str(tmp_path)]
    assert run.main(["--label", "first", *arguments]) == 0
    assert run.main(["--label", "second", "--top-k", "3", *arguments]) == 0

    with db() as session:  # the second run reused the processed documents
        count = session.scalar(select(func.count()).select_from(Document))
    assert count == len(corpus_files())

    first = json.loads((tmp_path / "first.json").read_text())
    second = json.loads((tmp_path / "second.json").read_text())
    assert (first["split"], first["settings"]["llm_model"]) == ("dev", "fake")
    assert second["settings"]["retrieval_top_k"] == 3
    assert len(first["questions"]) == 10
    record = first["questions"][0]
    assert {"score", "citations", "retrieved", "usage"} <= record.keys()
    assert all("text" not in chunk for chunk in record["retrieved"])  # saved without passages
    assert first["summary"]["questions"] == 10

    capsys.readouterr()
    report.main([str(tmp_path / "first.json"), str(tmp_path / "second.json")])
    tables = capsys.readouterr().out
    assert "| Metric | first (k=6) | second (k=3) |" in tables
    assert "| d01 |" in tables

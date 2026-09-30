"""The evaluation harness end to end, with the offline embedder and model."""

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Chunk, Document
from app.providers.factory import build_embedder
from evaluation import report, run
from evaluation.corpus_db import ingest_corpus
from evaluation.dataset import corpus_files, load_questions
from evaluation.metrics import contains_evidence
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
    dev_questions = len(load_questions().split("dev"))
    assert len(first["questions"]) == dev_questions
    record = first["questions"][0]
    assert {"score", "citations", "retrieved", "usage"} <= record.keys()
    assert all("text" not in chunk for chunk in record["retrieved"])  # saved without passages
    assert first["summary"]["questions"] == dev_questions

    capsys.readouterr()
    report.main([str(tmp_path / "first.json"), str(tmp_path / "second.json")])
    tables = capsys.readouterr().out
    default_k = first["settings"]["retrieval_top_k"]
    assert f"| Metric | first (k={default_k}) | second (k=3) |" in tables
    assert "| d01 |" in tables


@pytest.mark.usefixtures("offline_env")
def test_every_evidence_passage_is_inside_one_chunk(db: sessionmaker[Session]) -> None:
    """Evidence split across two chunks could never be retrieved whole, undercounting hit rate."""
    settings = get_settings()
    user_id = ingest_corpus(db, settings, build_embedder(settings, for_worker=True))
    chunks: dict[str, list[str]] = {}
    with db() as session:
        rows = session.execute(
            select(Document.filename, Chunk.text)
            .join(Chunk, Chunk.document_id == Document.id)
            .where(Document.owner_id == user_id)
        )
        for filename, text in rows:
            chunks.setdefault(filename, []).append(text)

    split = [
        question.id
        for question in load_questions().questions
        if question.evidence
        and not any(contains_evidence(text, question.evidence) for text in chunks[question.source])
    ]
    assert split == []

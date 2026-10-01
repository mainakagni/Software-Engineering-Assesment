"""The worker's job handling, driven directly (one job per call) against the real database."""

import json
import logging
import math
import re
from collections.abc import Sequence
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings
from app.db.models import Chunk, Document, DocumentBlob, IngestionJob, RateLimitCounter
from app.ingestion.pipeline import prepare_document
from app.logging_config import JsonFormatter
from app.providers.errors import ProviderError
from app.providers.fakes import FakeEmbedder
from app.ratelimit.budget import KEY
from app.worker.heartbeat import write_heartbeat
from app.worker.jobs import backoff_seconds, process_next_job
from app.worker.queue import claim_next_job, complete_job, requeue_stale_jobs
from tests.conftest import make_test_settings, signup
from tests.integration.test_documents_api import upload
from tests.pdf_factory import make_encrypted_pdf, make_pdf


class FailingEmbedder(FakeEmbedder):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    def embed_documents(self, texts: Sequence[str], title: str | None = None) -> list[list[float]]:
        raise self.error


def run_job(db: sessionmaker[Session], settings: Settings, embedder: Any = None) -> bool:
    return process_next_job(
        db, worker_id="test-worker", embedder=embedder or FakeEmbedder(), settings=settings
    )


def _document(db: sessionmaker[Session]) -> Document:
    with db() as session:
        return session.scalars(select(Document)).one()


def _job(db: sessionmaker[Session]) -> IngestionJob:
    with db() as session:
        return session.scalars(select(IngestionJob)).one()


def _count(db: sessionmaker[Session], model: type) -> int:
    with db() as session:
        return session.scalar(select(func.count()).select_from(model)) or 0


def test_empty_queue(db: sessionmaker[Session], settings: Settings) -> None:
    assert run_job(db, settings) is False


def test_text_file_becomes_ready_with_chunks(
    client: TestClient, db: sessionmaker[Session], settings: Settings
) -> None:
    upload(
        client, signup(client), "rules.txt", b"Hotel stays are capped at 180 dollars.\n\nMeals: 75."
    )
    assert run_job(db, settings) is True

    document = _document(db)
    assert (document.status, document.error, document.chunk_count) == ("ready", None, 1)
    assert document.page_count is None
    assert document.processed_at is not None
    assert _job(db).status == "done"
    assert _count(db, DocumentBlob) == 0  # bytes are dropped once processed

    with db() as session:
        chunk = session.scalars(select(Chunk)).one()
    assert chunk.owner_id == document.owner_id
    assert chunk.text.startswith("Hotel stays are capped")
    assert math.isclose(sum(v * v for v in chunk.embedding), 1.0, rel_tol=1e-5)


def test_markdown_sections_and_pdf_pages_are_stored(
    client: TestClient, db: sessionmaker[Session], settings: Settings
) -> None:
    headers = signup(client)
    upload(client, headers, "guide.md", b"# Travel\n## Lodging\nHotels up to 180 a night.")
    upload(client, headers, "policy.pdf", make_pdf(["Page one text.", "", "Page three text."]))
    assert run_job(db, settings) and run_job(db, settings)

    with db() as session:
        rows = session.execute(
            select(
                Document.filename,
                Document.page_count,
                Chunk.section,
                Chunk.page_start,
                Chunk.page_end,
            )
            .join(Chunk, Chunk.document_id == Document.id)
            .order_by(Document.filename)
        ).all()
    assert [tuple(row) for row in rows] == [
        ("guide.md", None, "Travel > Lodging", None, None),
        ("policy.pdf", 3, None, 1, 3),
    ]


def test_unreadable_pdf_fails_permanently_with_a_reason(
    client: TestClient, db: sessionmaker[Session], settings: Settings
) -> None:
    upload(client, signup(client), "locked.pdf", make_encrypted_pdf("secret"))
    run_job(db, settings)

    document = _document(db)
    assert (document.status, document.error) == ("failed", "The PDF is password-protected.")
    assert _job(db).status == "failed"
    assert _count(db, DocumentBlob) == 0
    assert run_job(db, settings) is False  # nothing left to retry


def test_provider_outage_is_retried_with_backoff_then_fails(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    settings = make_test_settings(job_max_attempts=2)
    upload(client, signup(client))
    outage = FailingEmbedder(ProviderError("gemini", "unavailable", "503", retryable=True))

    run_job(db, settings, outage)
    job, document = _job(db), _document(db)
    assert (job.status, job.attempts, document.status) == ("queued", 1, "queued")
    assert "unavailable" in (job.last_error or "")
    with db() as session:
        wait = session.scalar(select(IngestionJob.run_after - func.now()))
    assert wait is not None and wait > timedelta(seconds=10)

    _make_due(db)
    run_job(db, settings, outage)
    document = _document(db)
    assert (_job(db).status, document.status) == ("failed", "failed")
    assert "not responding" in (document.error or "")
    assert _count(db, DocumentBlob) == 0


def test_daily_quota_fails_at_once(
    client: TestClient, db: sessionmaker[Session], settings: Settings
) -> None:
    upload(client, signup(client))
    quota = FailingEmbedder(ProviderError("gemini", "quota_exhausted", "429", retryable=False))
    run_job(db, settings, quota)
    document = _document(db)
    assert document.status == "failed"
    assert "daily quota" in (document.error or "")


def test_unexpected_errors_are_retried(
    client: TestClient, db: sessionmaker[Session], settings: Settings
) -> None:
    upload(client, signup(client))
    run_job(db, settings, FailingEmbedder(RuntimeError("bug")))
    assert (_job(db).status, _document(db).status) == ("queued", "queued")

    _make_due(db)
    run_job(db, settings)
    assert _document(db).status == "ready"


def test_document_deleted_while_processing_is_dropped(
    client: TestClient, db: sessionmaker[Session], settings: Settings
) -> None:
    headers = signup(client)
    document = upload(client, headers)

    class DeletingEmbedder(FakeEmbedder):
        def embed_documents(
            self, texts: Sequence[str], title: str | None = None
        ) -> list[list[float]]:
            client.delete(f"/api/documents/{document['id']}", headers=headers)
            return super().embed_documents(texts, title)

    assert run_job(db, settings, DeletingEmbedder()) is True
    assert _count(db, Document) == 0
    assert _count(db, Chunk) == 0


class CountingEmbedder(FakeEmbedder):
    def __init__(self) -> None:
        super().__init__()
        self.calls = 0

    def embed_documents(self, texts: Sequence[str], title: str | None = None) -> list[list[float]]:
        self.calls += 1
        return super().embed_documents(texts, title)


def test_a_document_over_the_passage_limit_fails_before_embedding(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    settings = make_test_settings(
        max_chunks_per_document=2, chunk_size_chars=100, chunk_overlap_chars=0
    )
    text = " ".join(f"Sentence number {i} is here." for i in range(40))
    upload(client, signup(client), "long.txt", text.encode())
    embedder = CountingEmbedder()

    run_job(db, settings, embedder)

    document = _document(db)
    assert document.status == "failed"
    assert re.search(
        r"too long: it splits into \d+ passages, and the limit is 2\.", document.error or ""
    )
    assert embedder.calls == 0  # refused before anything was sent, so no quota was spent


def _paragraphs(topic: str, count: int) -> bytes:
    # Each paragraph is shorter than 100 characters and two are longer, so each is one passage.
    return "\n\n".join(
        f"The {topic} policy, part {i}, covers hotels, meals and taxis." for i in range(count)
    ).encode()


def _document_named(db: sessionmaker[Session], filename: str) -> Document:
    with db() as session:
        return session.scalars(select(Document).where(Document.filename == filename)).one()


def test_documents_share_a_daily_passage_budget(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    settings = make_test_settings(
        global_passages_per_day=5,
        max_chunks_per_document=5,
        chunk_size_chars=100,
        chunk_overlap_chars=0,
    )
    token = signup(client)
    upload(client, token, "first.txt", _paragraphs("travel", 3))
    run_job(db, settings)
    assert _document_named(db, "first.txt").chunk_count == 3

    upload(client, token, "second.txt", _paragraphs("expense", 3))
    embedder = CountingEmbedder()
    run_job(db, settings, embedder)

    second = _document_named(db, "second.txt")
    assert second.status == "failed"
    assert re.match(
        r"This document splits into 3 passages, but the demo's budget for processing documents "
        r"has room for only 2 more right now\. Delete it and upload it again in 2[34] hours, or "
        r"upload a shorter document\.$",
        second.error or "",
    )
    assert embedder.calls == 0  # refused before anything was sent, so no quota was spent

    upload(client, token, "third.txt", _paragraphs("meals", 1))
    run_job(db, settings)
    assert _document_named(db, "third.txt").status == "ready"  # the refused 3 were not counted


def test_a_used_up_passage_budget_says_so(client: TestClient, db: sessionmaker[Session]) -> None:
    settings = make_test_settings(
        global_passages_per_day=1,
        max_chunks_per_document=1,
        chunk_size_chars=100,
        chunk_overlap_chars=0,
    )
    token = signup(client)
    upload(client, token, "first.txt", _paragraphs("travel", 1))
    upload(client, token, "second.txt", _paragraphs("expense", 1))
    run_job(db, settings)
    run_job(db, settings)

    assert _document_named(db, "first.txt").status == "ready"
    second = _document_named(db, "second.txt")
    assert second.status == "failed"
    assert re.match(
        r"The demo's budget for processing documents is used up for now\. Delete this document "
        r"and upload it again in 2[34] hours\.$",
        second.error or "",
    )


def test_a_markdown_file_with_only_headings_fails_with_a_reason(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    upload(client, signup(client), "headings.md", b"# Travel\n\n## Hotels\n")
    run_job(db, make_test_settings())

    document = _document(db)
    assert (document.status, document.error) == (
        "failed",
        "The file has no text to search, only headings.",
    )
    assert _job(db).status == "failed"  # at once, not after retries
    with db() as session:
        assert (
            session.scalars(select(RateLimitCounter).where(RateLimitCounter.key == KEY)).all() == []
        )


def test_a_job_is_claimed_only_once(client: TestClient, db: sessionmaker[Session]) -> None:
    upload(client, signup(client))
    assert claim_next_job(db, "worker-a") is not None
    assert claim_next_job(db, "worker-b") is None
    assert _document(db).status == "processing"


def test_stale_jobs_are_requeued_or_failed(client: TestClient, db: sessionmaker[Session]) -> None:
    headers = signup(client)
    upload(client, headers, "a.txt", b"first")
    upload(client, headers, "b.txt", b"second")
    claim_next_job(db, "dead-worker")
    claim_next_job(db, "dead-worker")
    with db.begin() as session:
        session.execute(update(IngestionJob).values(locked_at=func.now() - timedelta(hours=1)))
        # one of them has already been tried too many times
        first = session.scalars(select(IngestionJob.id).order_by(IngestionJob.created_at)).first()
        session.execute(update(IngestionJob).where(IngestionJob.id == first).values(attempts=3))

    assert _requeue(db) == 2
    with db() as session:
        statuses = session.execute(
            select(Document.filename, Document.status).order_by(Document.filename)
        ).all()
    assert [tuple(s) for s in statuses] == [("a.txt", "failed"), ("b.txt", "queued")]


def test_recent_running_jobs_are_left_alone(client: TestClient, db: sessionmaker[Session]) -> None:
    upload(client, signup(client))
    claim_next_job(db, "busy-worker")
    assert _requeue(db) == 0
    assert _job(db).status == "running"


def test_long_jobs_of_a_live_worker_are_left_alone(
    client: TestClient, db: sessionmaker[Session]
) -> None:
    upload(client, signup(client))
    claim_next_job(db, "slow-worker")
    write_heartbeat(db, "slow-worker")
    _age_running_jobs(db)
    assert _requeue(db) == 0
    assert _job(db).status == "running"


def test_a_worker_that_lost_its_job_cannot_overwrite_the_new_owner(
    client: TestClient, db: sessionmaker[Session], settings: Settings
) -> None:
    upload(client, signup(client), "rules.txt", b"Hotels are capped at 180 dollars a night.")
    slow = claim_next_job(db, "slow-worker")
    assert slow is not None
    prepared = prepare_document(db, slow.document_id, FakeEmbedder(), settings)
    assert prepared is not None

    # The slow worker looked dead, so its job went back to the queue and another worker took it.
    _age_running_jobs(db)
    assert _requeue(db) == 1
    assert run_job(db, settings) is True
    assert _document(db).status == "ready"

    assert complete_job(db, slow, prepared) is False
    assert _count(db, Chunk) == 1
    assert _job(db).status == "done"


def _requeue(db: sessionmaker[Session]) -> int:
    return requeue_stale_jobs(
        db,
        stale_after=timedelta(minutes=10),
        worker_stale_after=timedelta(seconds=30),
        max_attempts=3,
    )


def _age_running_jobs(db: sessionmaker[Session]) -> None:
    with db.begin() as session:
        session.execute(
            update(IngestionJob)
            .where(IngestionJob.status == "running")
            .values(locked_at=func.now() - timedelta(hours=1))
        )


class _JsonLines(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.lines: list[dict[str, Any]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(json.loads(JsonFormatter().format(record)))


def test_worker_logs_carry_the_request_id_of_the_upload(
    client: TestClient, db: sessionmaker[Session], settings: Settings
) -> None:
    headers = {**signup(client), "X-Request-ID": "trace-from-upload"}
    upload(client, headers)
    capture = _JsonLines()
    worker_logger = logging.getLogger("app.worker")
    worker_logger.addHandler(capture)
    worker_logger.setLevel(logging.INFO)
    try:
        run_job(db, settings)
    finally:
        worker_logger.removeHandler(capture)
        worker_logger.setLevel(logging.NOTSET)
    events = {line["event"]: line for line in capture.lines}
    assert events["worker.job.claimed"]["request_id"] == "trace-from-upload"
    assert events["worker.job.done"]["request_id"] == "trace-from-upload"
    assert events["worker.job.done"]["chunk_count"] == 1


def test_backoff_grows() -> None:
    assert [backoff_seconds(n) for n in (1, 2, 3)] == [15, 60, 240]


def _make_due(db: sessionmaker[Session]) -> None:
    with db.begin() as session:
        session.execute(update(IngestionJob).values(run_after=func.now()))


@pytest.fixture(autouse=True)
def _quiet_pypdf() -> None:
    logging.getLogger("pypdf").setLevel(logging.ERROR)

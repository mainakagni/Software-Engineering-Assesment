"""Asking questions through the API, with the offline embedder and model."""

import json
import uuid
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Question
from app.providers.errors import ProviderError
from app.providers.fakes import FakeLLM
from app.providers.llm import LLMResult
from app.qa.grounding import NOT_FOUND_ANSWER
from app.qa.service import NO_DOCUMENTS_ANSWER
from app.worker.jobs import process_next_job
from tests.conftest import ClientFactory, signup
from tests.integration.test_documents_api import upload

TRAVEL = (
    b"# Travel policy\n## Flights\n"
    b"Domestic flights should be booked at least 7 business days in advance. "
    b"International flights must be booked at least 14 business days in advance.\n"
    b"## Lodging\nHotel stays are capped at 180 dollars per night in domestic locations.\n"
)
LEAVE = b"# Leave\nEmployees may take up to 25 paid sick days each year.\n"
FLIGHT_QUESTION = "How many business days in advance must international flights be booked?"


@pytest.fixture
def qa_client(client_factory: ClientFactory) -> TestClient:
    # Retries wait under a second: at most 0.5 s, then 1 s, with full jitter.
    return client_factory(retrieval_min_similarity=0.2, provider_max_retry_wait_seconds=1)


@pytest.fixture
def open_client(client_factory: ClientFactory) -> TestClient:
    """Every passage passes the first gate, so the model sees everything retrieval returns."""
    return client_factory(retrieval_min_similarity=-1.0)


def _process_all(client: TestClient, db: sessionmaker[Session]) -> None:
    settings = client.app.state.settings  # type: ignore[attr-defined]
    embedder = client.app.state.embedder  # type: ignore[attr-defined]
    while process_next_job(db, worker_id="test", embedder=embedder, settings=settings):
        pass


def _ready(
    client: TestClient, db: sessionmaker[Session], headers: dict[str, str], name: str, data: bytes
) -> dict[str, Any]:
    document = upload(client, headers, name, data)
    _process_all(client, db)
    return document


def _fake_llm(client: TestClient) -> FakeLLM:
    return client.app.state.llm  # type: ignore[attr-defined]


def _ask(
    client: TestClient, headers: dict[str, str], question: str = FLIGHT_QUESTION, **body: object
) -> Response:
    return client.post("/api/questions", headers=headers, json={"question": question, **body})


def test_answer_with_citations_usage_and_history(
    qa_client: TestClient, db: sessionmaker[Session]
) -> None:
    headers = signup(qa_client)
    document = _ready(qa_client, db, headers, "travel.md", TRAVEL)

    response = _ask(qa_client, headers)
    body = response.json()["data"]
    assert response.status_code == 200
    assert body["found"] is True
    assert "14 business days" in body["answer"]
    [citation] = body["citations"]
    assert citation["document_id"] == document["id"]
    assert citation["document_name"] == "travel.md"
    assert citation["section"] == "Travel policy > Flights"
    assert citation["quote_verified"] is True
    assert citation["quote"] in citation["passage"]
    assert 0 < citation["score"] <= 1

    usage = body["usage"]
    assert usage["model"] == "fake-llm"
    assert usage["prompt_tokens"] > 0 and usage["output_tokens"] > 0
    assert (
        usage["total_tokens"]
        == usage["prompt_tokens"] + usage["output_tokens"] + usage["thinking_tokens"]
    )
    assert usage["latency_ms"] >= usage["generation_ms"]
    assert usage["estimated_cost_usd"] > 0

    history = qa_client.get("/api/questions", headers=headers).json()
    assert history["meta"]["total"] == 1
    assert history["data"][0]["id"] == body["id"]
    assert qa_client.get(f"/api/questions/{body['id']}", headers=headers).json()["data"] == body


def test_without_ready_documents_nothing_is_called(qa_client: TestClient) -> None:
    headers = signup(qa_client)
    body = _ask(qa_client, headers).json()["data"]
    assert (body["found"], body["answer"]) == (False, NO_DOCUMENTS_ANSWER)
    assert _fake_llm(qa_client).calls == []


def test_off_topic_question_stops_at_the_retrieval_gate(
    client_factory: ClientFactory, db: sessionmaker[Session]
) -> None:
    client = client_factory(retrieval_min_similarity=0.5)
    headers = signup(client)
    _ready(client, db, headers, "travel.md", TRAVEL)
    body = _ask(client, headers, "Who won the football world cup in 1998?").json()["data"]
    assert (body["found"], body["answer"], body["citations"]) == (False, NOT_FOUND_ANSWER, [])
    assert body["usage"]["prompt_tokens"] == 0
    assert _fake_llm(client).calls == []


def test_model_saying_not_found_is_respected(
    qa_client: TestClient, db: sessionmaker[Session]
) -> None:
    headers = signup(qa_client)
    _ready(qa_client, db, headers, "travel.md", TRAVEL)
    _fake_llm(qa_client).queue(json.dumps({"found": False, "citations": [], "answer": "No."}))
    body = _ask(qa_client, headers).json()["data"]
    assert (body["found"], body["answer"]) == (False, NOT_FOUND_ANSWER)


def test_invented_citations_are_rejected(qa_client: TestClient, db: sessionmaker[Session]) -> None:
    headers = signup(qa_client)
    _ready(qa_client, db, headers, "travel.md", TRAVEL)
    invented = {
        "found": True,
        "citations": [{"source_id": "S1", "quote": "Flights can be booked the day before travel."}],
        "answer": "One day.",
    }
    _fake_llm(qa_client).queue(json.dumps(invented))
    assert _ask(qa_client, headers).json()["data"]["found"] is False


def test_a_malformed_reply_is_retried(qa_client: TestClient, db: sessionmaker[Session]) -> None:
    headers = signup(qa_client)
    _ready(qa_client, db, headers, "travel.md", TRAVEL)
    _fake_llm(qa_client).queue('{"found": tru')
    assert _ask(qa_client, headers).json()["data"]["found"] is True
    assert len(_fake_llm(qa_client).calls) == 2


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (ProviderError("gemini", "unavailable", "503", retryable=True), "not responding"),
        (ProviderError("gemini", "quota_exhausted", "429", retryable=False), "quota"),
    ],
)
def test_model_outage_is_a_clear_503(
    qa_client: TestClient, db: sessionmaker[Session], error: ProviderError, message: str
) -> None:
    headers = signup(qa_client)
    _ready(qa_client, db, headers, "travel.md", TRAVEL)
    _fake_llm(qa_client).queue(error, error, error)
    response = _ask(qa_client, headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "llm_unavailable"
    assert message in response.json()["error"]["message"]
    with db() as session:
        assert session.scalar(select(func.count()).select_from(Question)) == 0


def test_embedding_outage_is_a_clear_503(qa_client: TestClient, db: sessionmaker[Session]) -> None:
    headers = signup(qa_client)
    _ready(qa_client, db, headers, "travel.md", TRAVEL)

    def broken(_: str) -> list[float]:
        raise ProviderError("gemini", "timeout", "slow", retryable=True)

    qa_client.app.state.embedder.embed_query = broken  # type: ignore[attr-defined]
    response = _ask(qa_client, headers)
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "embedding_unavailable"


def test_no_transaction_stays_open_during_provider_calls(
    qa_client: TestClient, db: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    headers = signup(qa_client)
    _ready(qa_client, db, headers, "travel.md", TRAVEL)
    embedder, llm = qa_client.app.state.embedder, _fake_llm(qa_client)  # type: ignore[attr-defined]
    embed_query, generate_json = embedder.embed_query, llm.generate_json
    open_transactions: list[int] = []

    def count_open_transactions() -> None:
        with db() as session:
            open_transactions.append(
                session.execute(
                    text(
                        "SELECT count(*) FROM pg_stat_activity "
                        "WHERE datname = current_database() AND state = 'idle in transaction'"
                    )
                ).scalar_one()
            )

    def embed(question: str) -> list[float]:
        count_open_transactions()
        return embed_query(question)

    def generate(system: str, user: str, schema: dict[str, Any]) -> LLMResult:
        count_open_transactions()
        return generate_json(system, user, schema)

    monkeypatch.setattr(embedder, "embed_query", embed)
    monkeypatch.setattr(llm, "generate_json", generate)
    assert _ask(qa_client, headers).json()["data"]["found"] is True
    assert open_transactions == [0, 0]


def test_selected_documents_limit_the_search(
    open_client: TestClient, db: sessionmaker[Session]
) -> None:
    headers = signup(open_client)
    _ready(open_client, db, headers, "travel.md", TRAVEL)
    leave = _ready(open_client, db, headers, "leave.md", LEAVE)

    body = _ask(open_client, headers, document_ids=[leave["id"], leave["id"]]).json()["data"]
    assert body["document_ids"] == [leave["id"]]  # duplicates removed
    prompt = _fake_llm(open_client).calls[-1][1]
    assert "sick days" in prompt
    assert "International flights" not in prompt  # travel.md matches better but was not picked
    assert (body["found"], body["citations"]) == (False, [])


def test_selection_must_be_owned_and_ready(
    qa_client: TestClient, db: sessionmaker[Session]
) -> None:
    alice = signup(qa_client, "alice@example.com")
    bob = signup(qa_client, "bob@example.com")
    alices = _ready(qa_client, db, alice, "travel.md", TRAVEL)
    queued = upload(qa_client, bob, "leave.md", LEAVE)  # not processed yet

    assert _ask(qa_client, bob, document_ids=[alices["id"]]).status_code == 404
    assert _ask(qa_client, bob, document_ids=[str(uuid.uuid4())]).status_code == 404
    not_ready = _ask(qa_client, bob, document_ids=[queued["id"]])
    assert not_ready.status_code == 409


def test_retrieval_never_crosses_users(open_client: TestClient, db: sessionmaker[Session]) -> None:
    alice = signup(open_client, "alice@example.com")
    bob = signup(open_client, "bob@example.com")
    _ready(open_client, db, alice, "travel.md", TRAVEL)
    _ready(open_client, db, bob, "leave.md", LEAVE)

    body = _ask(open_client, bob).json()["data"]  # a question only Alice's document answers
    prompt = _fake_llm(open_client).calls[-1][1]
    assert "sick days" in prompt
    assert "International flights" not in prompt
    assert (body["found"], body["citations"]) == (False, [])


def test_history_is_private(qa_client: TestClient, db: sessionmaker[Session]) -> None:
    alice = signup(qa_client, "alice@example.com")
    bob = signup(qa_client, "bob@example.com")
    _ready(qa_client, db, alice, "travel.md", TRAVEL)
    question_id = _ask(qa_client, alice).json()["data"]["id"]
    assert qa_client.get(f"/api/questions/{question_id}", headers=bob).status_code == 404
    assert qa_client.get("/api/questions", headers=bob).json()["data"] == []


def test_deleted_documents_are_no_longer_searched_but_history_keeps_its_snapshot(
    open_client: TestClient, db: sessionmaker[Session]
) -> None:
    headers = signup(open_client)
    travel = _ready(open_client, db, headers, "travel.md", TRAVEL)
    _ready(open_client, db, headers, "leave.md", LEAVE)
    before = _ask(open_client, headers).json()["data"]
    assert before["found"]

    assert open_client.delete(f"/api/documents/{travel['id']}", headers=headers).status_code == 204
    after = _ask(open_client, headers).json()["data"]
    assert "International flights" not in _fake_llm(open_client).calls[-1][1]
    assert (after["found"], after["citations"]) == (False, [])
    kept = open_client.get(f"/api/questions/{before['id']}", headers=headers).json()["data"]
    assert kept["citations"] == before["citations"]


@pytest.mark.parametrize(
    "body",
    [
        {"question": "  "},
        {"question": "x" * 1001},
        {"question": "Valid question?", "document_ids": [str(uuid.uuid4()) for _ in range(21)]},
        {"question": "Valid question?", "document_ids": ["not-a-uuid"]},
        {"question": "Valid question?", "document_ids": []},
        {},
    ],
    ids=["blank", "too-long", "too-many-documents", "bad-id", "empty-selection", "missing"],
)
def test_question_validation(qa_client: TestClient, body: dict[str, Any]) -> None:
    response = qa_client.post("/api/questions", headers=signup(qa_client), json=body)
    assert response.status_code == 422


def test_validation_messages_are_written_for_people(qa_client: TestClient) -> None:
    headers = signup(qa_client)
    short = qa_client.post("/api/questions", headers=headers, json={"question": " hi "})
    empty = qa_client.post(
        "/api/questions", headers=headers, json={"question": "Valid?", "document_ids": []}
    )
    assert short.json()["error"]["details"] == [
        {"field": "question", "message": "Ask a question of at least 3 characters."}
    ]
    assert empty.json()["error"]["details"][0]["message"].startswith("Select at least one")


def test_questions_require_login(qa_client: TestClient) -> None:
    assert qa_client.post("/api/questions", json={"question": "Anything?"}).status_code == 401
    assert qa_client.get("/api/questions").status_code == 401

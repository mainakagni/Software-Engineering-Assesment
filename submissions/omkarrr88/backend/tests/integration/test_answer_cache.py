"""The answer cache: repeated questions about unchanged documents reuse the stored answer."""

import json
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.providers.fakes import FakeLLM
from tests.conftest import ClientFactory, signup
from tests.integration.test_questions_api import FLIGHT_QUESTION, LEAVE, TRAVEL, _ready


def _answer(client: TestClient, headers: dict[str, str], question: str, **body: Any) -> Any:
    response = client.post("/api/questions", headers=headers, json={"question": question, **body})
    assert response.status_code == 200, response.text
    return response.json()["data"]


def _llm(client: TestClient) -> FakeLLM:
    return client.app.state.llm  # type: ignore[attr-defined]


def test_repeated_question_is_served_from_the_cache(
    client_factory: ClientFactory, db: sessionmaker[Session]
) -> None:
    client = client_factory(retrieval_min_similarity=0.2)
    headers = signup(client)
    _ready(client, db, headers, "travel.md", TRAVEL)

    first = _answer(client, headers, FLIGHT_QUESTION)
    again = _answer(client, headers, "  " + FLIGHT_QUESTION.upper())
    assert len(_llm(client).calls) == 1
    assert (first["cached"], again["cached"]) == (False, True)
    assert (again["answer"], again["citations"]) == (first["answer"], first["citations"])
    assert again["id"] != first["id"]
    assert (again["usage"]["total_tokens"], again["usage"]["estimated_cost_usd"]) == (0, 0)

    # A new document changes what could be cited, so the stored answer is not reused.
    _ready(client, db, headers, "leave.md", LEAVE)
    assert _answer(client, headers, FLIGHT_QUESTION)["cached"] is False
    assert len(_llm(client).calls) == 2
    assert client.get("/api/questions", headers=headers).json()["meta"]["total"] == 3


def test_cache_is_per_user_and_per_selection(
    client_factory: ClientFactory, db: sessionmaker[Session]
) -> None:
    client = client_factory(retrieval_min_similarity=0.2)
    alice = signup(client, "alice@example.com")
    travel = _ready(client, db, alice, "travel.md", TRAVEL)
    _answer(client, alice, FLIGHT_QUESTION)
    selected = _answer(client, alice, FLIGHT_QUESTION, document_ids=[travel["id"]])
    assert selected["cached"] is False

    bob = signup(client, "bob@example.com")
    _ready(client, db, bob, "travel.md", TRAVEL)
    assert _answer(client, bob, FLIGHT_QUESTION)["cached"] is False
    assert len(_llm(client).calls) == 3


def test_refusals_are_not_cached(client_factory: ClientFactory, db: sessionmaker[Session]) -> None:
    client = client_factory(retrieval_min_similarity=0.2)
    headers = signup(client)
    _ready(client, db, headers, "travel.md", TRAVEL)
    _llm(client).queue(json.dumps({"found": False, "citations": [], "answer": "No."}))

    assert _answer(client, headers, FLIGHT_QUESTION)["found"] is False
    retried = _answer(client, headers, FLIGHT_QUESTION)
    assert (retried["found"], retried["cached"]) == (True, False)
    assert _answer(client, headers, FLIGHT_QUESTION)["cached"] is True


def test_the_cache_can_be_switched_off(
    client_factory: ClientFactory, db: sessionmaker[Session]
) -> None:
    client = client_factory(retrieval_min_similarity=0.2, answer_cache_ttl_hours=0)
    headers = signup(client)
    _ready(client, db, headers, "travel.md", TRAVEL)
    answers = [_answer(client, headers, FLIGHT_QUESTION) for _ in range(2)]
    assert [answer["cached"] for answer in answers] == [False, False]
    assert len(_llm(client).calls) == 2

"""
Question endpoint tests — Q&A with mocked LLM/embeddings (no API keys in CI)
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_ask_without_documents_returns_refused(client: AsyncClient, auth_headers: dict):
    """When no documents are ready, LLM refuses."""
    mock_embedding = [0.1] * 768
    mock_llm_result = MagicMock()
    mock_llm_result.answer = "I couldn't find this in your documents."
    mock_llm_result.was_refused = True
    mock_llm_result.tokens_used = 10
    mock_llm_result.latency_ms = 50.0
    mock_llm_result.estimated_cost_usd = 0.000001

    with patch("app.routers.questions.embed_query", new=AsyncMock(return_value=mock_embedding)), \
         patch("app.routers.questions.generate_answer", new=AsyncMock(return_value=mock_llm_result)):
        resp = await client.post(
            "/api/v1/questions",
            headers=auth_headers,
            json={"question": "What is the refund policy?"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["was_refused"] is True
    assert "I couldn't find" in data["answer"]
    assert data["citations"] == []


@pytest.mark.asyncio
async def test_ask_with_answer(client: AsyncClient, auth_headers: dict):
    """When chunks exist, returns grounded answer with citations."""
    mock_embedding = [0.1] * 768
    mock_llm_result = MagicMock()
    mock_llm_result.answer = "The refund policy allows returns within 30 days."
    mock_llm_result.was_refused = False
    mock_llm_result.tokens_used = 200
    mock_llm_result.latency_ms = 800.0
    mock_llm_result.estimated_cost_usd = 0.000015

    with patch("app.routers.questions.embed_query", new=AsyncMock(return_value=mock_embedding)), \
         patch("app.routers.questions.retrieve_chunks", new=AsyncMock(return_value=[])), \
         patch("app.routers.questions.generate_answer", new=AsyncMock(return_value=mock_llm_result)):
        resp = await client.post(
            "/api/v1/questions",
            headers=auth_headers,
            json={"question": "What is the refund policy?"},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["was_refused"] is False
    assert "30 days" in data["answer"]


@pytest.mark.asyncio
async def test_get_question_history(client: AsyncClient, auth_headers: dict):
    """Question history is returned for the authenticated user."""
    resp = await client.get("/api/v1/questions", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "items" in data
    assert "total" in data


@pytest.mark.asyncio
async def test_question_invalid_document_id(client: AsyncClient, auth_headers: dict):
    """Providing a non-existent document_id returns 404."""
    resp = await client.post(
        "/api/v1/questions",
        headers=auth_headers,
        json={"question": "Hello", "document_ids": ["00000000-0000-0000-0000-000000000000"]},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_question_history_isolation(
    client: AsyncClient,
    auth_headers: dict,
    second_auth_headers: dict,
):
    """User B cannot see User A's question history."""
    # Ask question as user A (mocked)
    mock_emb = [0.1] * 768
    mock_result = MagicMock(answer="Test answer", was_refused=False, tokens_used=50, latency_ms=100.0, estimated_cost_usd=None)
    with patch("app.routers.questions.embed_query", new=AsyncMock(return_value=mock_emb)), \
         patch("app.routers.questions.retrieve_chunks", new=AsyncMock(return_value=[])), \
         patch("app.routers.questions.generate_answer", new=AsyncMock(return_value=mock_result)):
        await client.post("/api/v1/questions", headers=auth_headers, json={"question": "User A secret question"})

    # User B's history should not contain User A's question
    resp_b = await client.get("/api/v1/questions", headers=second_auth_headers)
    questions_b = [q["question"] for q in resp_b.json()["items"]]
    assert "User A secret question" not in questions_b

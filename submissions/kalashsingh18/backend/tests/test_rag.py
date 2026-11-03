import uuid
from unittest.mock import patch
from app.models.document import Document
from app.models.chunk import DocumentChunk


def test_grounded_qa_integration_flow(client, db, user_a, auth_headers_user_a):
    """
    Integration test for the full Q&A flow with the LLM mocked.
    Ensures CI pipelines pass without requiring real external API keys.
    """
    # 1. Setup a ready document and chunk for User A
    doc = Document(
        id=uuid.uuid4(),
        user_id=user_a.id,
        filename="company_policy.pdf",
        file_type="pdf",
        file_size=2048,
        status="ready"
    )
    db.add(doc)

    chunk = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        user_id=user_a.id,
        chunk_index=0,
        page_number=3,
        content="All full-time employees are eligible for 25 days of paid annual vacation leave.",
        embedding=[0.1] * 768
    )
    db.add(chunk)
    db.commit()

    # Mock the LLM generation function to return a deterministic cited answer
    with patch("app.services.rag_service.generate_grounded_answer") as mock_generate:
        mock_generate.return_value = (
            "Employees receive 25 days of paid annual vacation leave [Doc: company_policy.pdf, Page: 3].",
            {
                "prompt_tokens": 120,
                "completion_tokens": 30,
                "total_tokens": 150,
                "latency_ms": 340.5,
                "estimated_cost_usd": 0.00002
            }
        )

        res = client.post(
            "/api/v1/questions/ask",
            headers=auth_headers_user_a,
            json={"question": "How many days of annual leave do employees get?"}
        )

        assert res.status_code == 200
        data = res.json()
        assert "25 days of paid annual vacation" in data["answer"]
        assert len(data["citations"]) > 0
        assert data["citations"][0]["document_name"] == "company_policy.pdf"
        assert data["citations"][0]["page_number"] == 3
        assert data["usage"]["latency_ms"] == 340.5
        assert data["grounded"] is True

    # 2. Check query history is recorded
    hist_res = client.get("/api/v1/questions/history", headers=auth_headers_user_a)
    assert hist_res.status_code == 200
    history = hist_res.json()
    assert len(history) >= 1
    assert history[0]["question"] == "How many days of annual leave do employees get?"


def test_unanswerable_question_refusal(client, db, user_a, auth_headers_user_a):
    """
    Verifies that unanswerable questions receive an explicit honest refusal
    instead of hallucinations.
    """
    with patch("app.services.rag_service.generate_grounded_answer") as mock_generate:
        mock_generate.return_value = (
            "I could not find an answer in your uploaded documents.",
            {
                "prompt_tokens": 50,
                "completion_tokens": 10,
                "total_tokens": 60,
                "latency_ms": 150.0,
                "estimated_cost_usd": 0.0
            }
        )

        res = client.post(
            "/api/v1/questions/ask",
            headers=auth_headers_user_a,
            json={"question": "What is the secret launch date of project alpha?"}
        )

        assert res.status_code == 200
        data = res.json()
        assert data["answer"] == "I could not find an answer in your uploaded documents."
        assert data["grounded"] is False
        assert len(data["citations"]) == 0


def test_out_of_context_question_refusal(client, db, user_a, auth_headers_user_a):
    """
    Verifies that questions unrelated to uploaded documents or history
    receive the OUT_OF_CONTEXT_MESSAGE with grounded=False.
    """
    from app.rag.generator import OUT_OF_CONTEXT_MESSAGE

    with patch("app.services.rag_service.generate_grounded_answer") as mock_generate:
        mock_generate.return_value = (
            OUT_OF_CONTEXT_MESSAGE,
            {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
                "latency_ms": 10.0,
                "estimated_cost_usd": 0.0
            }
        )

        res = client.post(
            "/api/v1/questions/ask",
            headers=auth_headers_user_a,
            json={"question": "What is the capital of France?"}
        )

        assert res.status_code == 200
        data = res.json()
        assert data["answer"] == OUT_OF_CONTEXT_MESSAGE
        assert data["grounded"] is False
        assert len(data["citations"]) == 0


def test_general_query_document_comparison():
    """
    Verifies that general or comparative queries synthesize across retrieved chunks
    and compare with the document rather than refusing.
    """
    from app.rag.generator import generate_grounded_answer, REFUSAL_MESSAGE, OUT_OF_CONTEXT_MESSAGE

    chunks = [
        {
            "chunk_id": uuid.uuid4(),
            "document_id": uuid.uuid4(),
            "document_name": "leave_policy.pdf",
            "page_number": 1,
            "content": "Employees get 25 days paid vacation leave annually."
        },
        {
            "chunk_id": uuid.uuid4(),
            "document_id": uuid.uuid4(),
            "document_name": "contractor_policy.pdf",
            "page_number": 2,
            "content": "Contractors are not eligible for paid vacation leave."
        }
    ]

    # Test comparative query
    ans, usage = generate_grounded_answer(
        question="What is the difference between the leave policy and contractor policy?",
        retrieved_chunks=chunks
    )
    assert ans != REFUSAL_MESSAGE
    assert ans != OUT_OF_CONTEXT_MESSAGE
    assert "leave_policy.pdf" in ans or "contractor_policy.pdf" in ans

    # Test general query comparing with document
    general_chunks = [chunks[0]]
    ans2, usage2 = generate_grounded_answer(
        question="What is the general concept of annual leave and what does the document say?",
        retrieved_chunks=general_chunks
    )
    assert ans2 != REFUSAL_MESSAGE
    assert ans2 != OUT_OF_CONTEXT_MESSAGE
    assert "leave_policy.pdf" in ans2



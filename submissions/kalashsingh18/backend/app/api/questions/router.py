from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.user import User
from app.utils.security import get_current_user
from app.utils.rate_limiter import check_rate_limit
from tenacity import retry, stop_after_attempt, wait_exponential
from app.api.questions.schemas import (
    QuestionRequest,
    QuestionResponse,
    QueryLogResponse
)
from app.services.rag_service import answer_question, get_user_query_history

router = APIRouter(prefix="/questions", tags=["Questions & RAG"])


@router.post("/ask", response_model=QuestionResponse)
def ask(
    data: QuestionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
   
    check_rate_limit(str(current_user.id))

    history = None
    if data.chat_history:
        history = [{"role": t.role, "content": t.content} for t in data.chat_history]

    return answer_question(
        db=db,
        user_id=current_user.id,
        question=data.question,
        document_ids=data.document_ids,
        chat_history=history
    )


@router.post("/stream")
def stream_ask(
    data: QuestionRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    from fastapi.responses import StreamingResponse
    from app.utils.embeddings import get_query_embedding
    from app.rag.vector_store import search_similar_chunks
    from app.rag.generator import stream_grounded_answer

    check_rate_limit(str(current_user.id))

    query_vec = get_query_embedding(data.question)
    retrieved = search_similar_chunks(
        db=db,
        user_id=current_user.id,
        query_vector=query_vec,
        top_k=6,
        document_ids=data.document_ids
    )

    history = None
    if data.chat_history:
        history = [{"role": t.role, "content": t.content} for t in data.chat_history]

    return StreamingResponse(
        stream_grounded_answer(data.question, retrieved, chat_history=history),
        media_type="text/event-stream"
    )


@router.get("/history", response_model=List[QueryLogResponse])
def get_history(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return get_user_query_history(db, current_user.id)


@router.post("/suggestions")
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
def get_followup_suggestions(
    data: dict,
    current_user: User = Depends(get_current_user),
):
    import json
    import httpx
    from app.config import settings

    question = data.get("question", "")
    answer = data.get("answer", "")

    if not question or not answer:
        return {"suggestions": []}

    prompt = f"""Based on this Q&A exchange, generate exactly 3 short, specific follow-up questions the user might want to ask next. Return ONLY a JSON array of 3 strings, nothing else.

Question: {question[:500]}
Answer: {answer[:800]}

Return format: ["question 1", "question 2", "question 3"]"""

    if settings.LLM_PROVIDER == "groq" and settings.GROQ_API_KEY:
        try:
            url = f"{settings.GROQ_API_BASE.rstrip('/')}/chat/completions"
            headers = {
                "Authorization": f"Bearer {settings.GROQ_API_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": settings.GROQ_MODEL,
                "messages": [
                    {"role": "system", "content": "You generate follow-up questions. Return ONLY a JSON array of 3 strings."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.7,
                "max_tokens": 256
            }
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                text = resp.json()["choices"][0]["message"]["content"].strip()
                suggestions = json.loads(text)
                if isinstance(suggestions, list) and len(suggestions) >= 3:
                    return {"suggestions": suggestions[:3]}
        except Exception:
            pass

    return {"suggestions": [
        f"Can you explain more about {question.split()[-2] if len(question.split()) > 2 else 'this'}?",
        "What are the key details I should know?",
        "Are there any exceptions or special cases?"
    ]}


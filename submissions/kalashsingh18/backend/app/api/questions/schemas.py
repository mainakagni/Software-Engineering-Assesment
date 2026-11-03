import uuid
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class ChatTurn(BaseModel):
    role: str = Field(..., pattern="^(user|assistant)$")
    content: str


class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=2, max_length=1000)
    document_ids: Optional[List[uuid.UUID]] = None
    chat_history: Optional[List[ChatTurn]] = None


class CitationItem(BaseModel):
    document_id: str
    document_name: str
    page_number: int
    passage: str


class UsageStats(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    latency_ms: float = 0.0
    estimated_cost_usd: float = 0.0


class QuestionResponse(BaseModel):
    question: str
    answer: str
    citations: List[CitationItem] = []
    usage: UsageStats
    grounded: bool = True


class QueryLogResponse(BaseModel):
    id: uuid.UUID
    question: str
    answer: str
    citations: List[Dict[str, Any]]
    prompt_tokens: int
    completion_tokens: int
    latency_ms: float
    estimated_cost: float
    created_at: datetime

    class Config:
        from_attributes = True

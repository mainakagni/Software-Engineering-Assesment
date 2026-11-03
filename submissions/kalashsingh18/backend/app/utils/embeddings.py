import hashlib
import logging
import math
from typing import List
from tenacity import retry, stop_after_attempt, wait_exponential
from app.config import settings

logger = logging.getLogger("documind.embeddings")


def _deterministic_mock_embedding(text: str, dim: int = 768) -> List[float]:
    raw_hash = hashlib.sha256(text.encode("utf-8")).digest()
    vec = []
    for i in range(dim):
        byte_val = raw_hash[i % len(raw_hash)]
        val = math.sin((byte_val + 1) * (i + 1))
        vec.append(val)
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    reraise=True
)
def get_embedding(text: str) -> List[float]:

    if not text.strip():
        return [0.0] * settings.EMBEDDING_DIMENSION

    if settings.LLM_PROVIDER == "gemini" and settings.GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            
            result = genai.embed_content(
                model=settings.EMBEDDING_MODEL,
                content=text,
                task_type="retrieval_document"
            )
            embedding = result.get("embedding", [])
            if embedding:
                return embedding
        except Exception as e:
            logger.warning(f"Gemini embedding API call failed: {e}. Falling back to fallback vector.")

    return _deterministic_mock_embedding(text, settings.EMBEDDING_DIMENSION)


def get_query_embedding(query: str) -> List[float]:
    if settings.LLM_PROVIDER == "gemini" and settings.GEMINI_API_KEY:
        try:
            import google.generativeai as genai
            genai.configure(api_key=settings.GEMINI_API_KEY)
            
            result = genai.embed_content(
                model=settings.EMBEDDING_MODEL,
                content=query,
                task_type="retrieval_query"
            )
            embedding = result.get("embedding", [])
            if embedding:
                return embedding
        except Exception as e:
            logger.warning(f"Gemini query embedding call failed: {e}. Falling back to fallback vector.")

    return _deterministic_mock_embedding(query, settings.EMBEDDING_DIMENSION)

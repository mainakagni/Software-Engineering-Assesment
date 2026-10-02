"""
Embedder Service — Google Gemini text-embedding-004 / gemini-embedding-001
Produces 768-dimensional embeddings for text chunks and queries.
"""
from __future__ import annotations
import logging
import asyncio
from typing import List

from google import genai
from google.genai.types import EmbedContentConfig

from app.config import settings

logger = logging.getLogger(__name__)

_client = None


def _get_client() -> genai.Client:
    """Lazily create and return a Gemini client."""
    global _client
    if _client is None and settings.gemini_api_key:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _embed_content_sync(client: genai.Client, model: str, contents, task_type: str):
    """Call embed_content with fallback to gemini-embedding-001 (768-dim)."""
    try:
        return client.models.embed_content(
            model=model,
            contents=contents,
            config=EmbedContentConfig(task_type=task_type, output_dimensionality=768),
        )
    except Exception as exc:
        if "404" in str(exc) or "NOT_FOUND" in str(exc) or "not found" in str(exc).lower():
            return client.models.embed_content(
                model="gemini-embedding-001",
                contents=contents,
                config=EmbedContentConfig(task_type=task_type, output_dimensionality=768),
            )
        raise


async def embed_texts(texts: List[str]) -> List[List[float]]:
    """
    Embed a list of text strings.
    Returns a list of 768-dimensional float vectors.
    """
    client = _get_client()
    if not texts or not client:
        return []

    BATCH_SIZE = 100
    all_embeddings: List[List[float]] = []

    for i in range(0, len(texts), BATCH_SIZE):
        batch = texts[i : i + BATCH_SIZE]
        try:
            result = await asyncio.to_thread(
                _embed_content_sync,
                client,
                settings.gemini_embedding_model,
                batch,
                "RETRIEVAL_DOCUMENT",
            )
            all_embeddings.extend([e.values for e in result.embeddings])
        except Exception as exc:
            logger.error(f"Embedding batch {i}–{i+len(batch)} failed: {exc}", extra={"error": str(exc)})
            raise

    return all_embeddings


async def embed_query(query: str) -> List[float]:
    """Embed a single query string for retrieval."""
    client = _get_client()
    if not client:
        raise RuntimeError("Gemini API key not configured")
    try:
        result = await asyncio.to_thread(
            _embed_content_sync,
            client,
            settings.gemini_embedding_model,
            query,
            "RETRIEVAL_QUERY",
        )
        return result.embeddings[0].values
    except Exception as exc:
        logger.error(f"Query embedding failed: {exc}", extra={"error": str(exc)})
        raise

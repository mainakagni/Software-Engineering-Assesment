"""
Health Router — database, vector store, and worker connectivity check
GET /health
"""
import logging
import os

from fastapi import APIRouter
from sqlalchemy import text

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check() -> dict:
    """
    Check connectivity to PostgreSQL (database + vector extension) and Redis (worker queue).
    Returns status: healthy | degraded
    """
    from app.config import settings

    db_status = "ok"
    vector_status = "ok"
    worker_status = "ok"

    # Check PostgreSQL + pgvector
    try:
        from app.database import engine
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
            # Check pgvector
            result = await conn.execute(text("SELECT extname FROM pg_extension WHERE extname = 'vector'"))
            if not result.fetchone():
                vector_status = "extension not installed"
    except Exception as exc:
        db_status = f"error: {exc}"
        vector_status = "error: db unreachable"

    # Check Redis (Celery broker)
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
    except Exception as exc:
        worker_status = f"error: {exc}"

    overall = "healthy" if all(s == "ok" for s in [db_status, vector_status, worker_status]) else "degraded"

    return {
        "status": overall,
        "database": db_status,
        "vector_store": vector_status,
        "worker_queue": worker_status,
        "version": "1.0.0",
    }

"""
DocuMind — FastAPI Application Entry Point
"""
from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.config import settings
from app.database import engine, Base
from app.logging_config import setup_logging
from app.routers import auth, documents, questions, health
from app.routers.questions import limiter

setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting DocuMind API", extra={"event": "startup"})
    try:
        async with engine.begin() as conn:
            # Enable pgvector extension
            await conn.execute(__import__("sqlalchemy").text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database ready", extra={"event": "startup"})

        # Seed default user if not exists
        try:
            from app.database import AsyncSessionLocal
            from app.models import User
            from app.auth import hash_password
            from sqlalchemy import select
            import uuid

            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(User).where(User.email == "aman123@gmail.com")
                )
                if not result.scalar_one_or_none():
                    user = User(
                        id=uuid.uuid4(),
                        email="aman123@gmail.com",
                        username="aman123",
                        hashed_password=hash_password("Aman@123"),
                    )
                    session.add(user)
                    await session.commit()
                    logger.info("Default user created: aman123@gmail.com")
                else:
                    logger.info("Default user already exists")
        except Exception as exc:
            logger.warning(f"Could not seed default user: {exc}")
    except Exception as exc:
        logger.warning(f"Database connection failed during startup: {exc}. Server will start in degraded mode.")

    yield
    logger.info("Shutting down DocuMind API", extra={"event": "shutdown"})


app = FastAPI(
    title="DocuMind API",
    description="AI Knowledge Assistant — DocuMind (amanaryan2005)",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# Rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(health.router)
app.include_router(auth.router, prefix="/api/v1")
app.include_router(documents.router, prefix="/api/v1")
app.include_router(questions.router, prefix="/api/v1")

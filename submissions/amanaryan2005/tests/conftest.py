"""
pytest fixtures for DocuMind backend tests.
Uses an in-memory SQLite-compatible test DB for fast unit tests,
and mocks external services (Gemini, Celery).
"""
import asyncio
import os
import sys
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, patch, MagicMock

# Add backend and root directories to sys.path
root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
backend_path = os.path.join(root_path, "backend")
if root_path not in sys.path:
    sys.path.insert(0, root_path)
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import text

from app.database import Base, get_db
from app.config import settings
from main import app as fastapi_app
from app import models as _models

from sqlalchemy.pool import StaticPool
from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

# Use in-memory SQLite by default for fast, isolated unit tests (or PostgreSQL if TEST_DATABASE_URL is set)
TEST_DB_URL = os.getenv("TEST_DATABASE_URL", "sqlite+aiosqlite:///:memory:")
test_connect_args = {}

if TEST_DB_URL.startswith("postgresql://"):
    TEST_DB_URL = TEST_DB_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

if "postgresql" in TEST_DB_URL:
    if "sslmode=" in TEST_DB_URL or "channel_binding=" in TEST_DB_URL or "neon.tech" in TEST_DB_URL:
        parsed = urlparse(TEST_DB_URL)
        query_params = parse_qs(parsed.query)
        sslmode = query_params.pop("sslmode", [None])[0]
        query_params.pop("channel_binding", None)
        new_query = urlencode(query_params, doseq=True)
        TEST_DB_URL = urlunparse(parsed._replace(query=new_query))
        if sslmode or "neon.tech" in TEST_DB_URL:
            test_connect_args["ssl"] = "require"
    test_engine = create_async_engine(TEST_DB_URL, connect_args=test_connect_args, poolclass=NullPool, echo=False)
else:
    test_engine = create_async_engine(TEST_DB_URL, connect_args={"check_same_thread": False}, poolclass=StaticPool, echo=False)

TestSession = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def mock_celery():
    with patch("app.routers.documents._celery_app.send_task") as mock_send:
        mock_task = MagicMock()
        mock_task.id = "mock-task-id-12345"
        mock_send.return_value = mock_task
        yield mock_send


@pytest_asyncio.fixture(scope="session", autouse=True)
async def create_tables():
    db_available = False
    try:
        async with test_engine.begin() as conn:
            if "postgresql" in TEST_DB_URL:
                await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
            await conn.run_sync(Base.metadata.create_all)
        db_available = True
    except Exception as exc:
        print(f"\n[conftest] Note: DB setup failed ({exc}).")

    yield

    if db_available:
        try:
            async with test_engine.begin() as conn:
                await conn.run_sync(Base.metadata.drop_all)
            await test_engine.dispose()
        except Exception:
            pass


@pytest_asyncio.fixture
async def db():
    async with TestSession() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client():
    async def override_db():
        async with TestSession() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    fastapi_app.dependency_overrides[get_db] = override_db
    async with AsyncClient(transport=ASGITransport(app=fastapi_app), base_url="http://test") as c:
        yield c
    fastapi_app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def auth_headers(client: AsyncClient):
    """Register and log in a test user, return auth headers."""
    await client.post("/api/v1/auth/signup", json={
        "email": "test@example.com",
        "username": "testuser",
        "password": "testpassword123"
    })
    resp = await client.post("/api/v1/auth/login", json={
        "username": "testuser",
        "password": "testpassword123"
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def second_auth_headers(client: AsyncClient):
    """Second user — for isolation tests."""
    await client.post("/api/v1/auth/signup", json={
        "email": "other@example.com",
        "username": "otheruser",
        "password": "otherpassword123"
    })
    resp = await client.post("/api/v1/auth/login", json={
        "username": "otheruser",
        "password": "otherpassword123"
    })
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}

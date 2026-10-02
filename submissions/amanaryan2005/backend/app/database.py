"""
Database — async SQLAlchemy with pgvector support
"""

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


from urllib.parse import urlparse, parse_qs, urlencode, urlunparse

DATABASE_URL = settings.database_url
connect_args = {}

if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

if "sslmode=" in DATABASE_URL or "channel_binding=" in DATABASE_URL or "neon.tech" in DATABASE_URL:
    parsed = urlparse(DATABASE_URL)
    query_params = parse_qs(parsed.query)
    sslmode = query_params.pop("sslmode", [None])[0]
    query_params.pop("channel_binding", None)
    new_query = urlencode(query_params, doseq=True)
    DATABASE_URL = urlunparse(parsed._replace(query=new_query))
    if sslmode or "neon.tech" in DATABASE_URL:
        connect_args["ssl"] = "require"

engine = create_async_engine(
    DATABASE_URL,
    connect_args=connect_args,
    echo=(settings.environment == "development"),
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    __allow_unmapped__ = True


async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
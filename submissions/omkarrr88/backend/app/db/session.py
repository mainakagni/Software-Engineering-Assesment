from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import Settings


def make_session_factory(settings: Settings) -> sessionmaker[Session]:
    """One engine (and connection pool) per process; sessions are cheap and short-lived."""
    engine = create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        connect_args={"connect_timeout": 5},
    )
    return sessionmaker(bind=engine, expire_on_commit=False)

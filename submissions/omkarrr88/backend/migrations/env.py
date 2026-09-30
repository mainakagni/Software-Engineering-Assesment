"""Alembic runs migrations online only, against DATABASE_URL (or a URL passed in by tests)."""

from alembic import context
from sqlalchemy import create_engine, pool, text

from app.config import get_settings
from app.db import models  # noqa: F401  (imports the tables into Base.metadata)
from app.db.base import Base
from app.logging_config import configure_logging

# Any fixed number works; every process that migrates must use the same one.
MIGRATION_LOCK_ID = 20260930


def run_migrations() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    url = context.config.attributes.get("database_url") or settings.database_url

    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            # Two containers starting at the same time must not both run migrations. The lock is
            # held until this transaction commits.
            connection.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": MIGRATION_LOCK_ID})
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("Offline (SQL script) migrations are not supported.")
run_migrations()

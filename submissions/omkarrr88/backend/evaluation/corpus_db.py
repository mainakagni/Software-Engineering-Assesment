"""The evaluation account: its own database, one user, and the corpus processed by the worker."""

import logging
import secrets
import time
import uuid
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session, sessionmaker

from app.auth.service import register_user
from app.config import Settings
from app.db.models import Document, User
from app.documents.service import create_document
from app.documents.validation import validate_upload
from app.providers.embeddings import Embedder
from app.worker.jobs import process_next_job
from evaluation.dataset import corpus_files

logger = logging.getLogger(__name__)

BACKEND_DIR = Path(__file__).resolve().parent.parent
EVAL_EMAIL = "evaluation@documind.local"
PROCESSING_TIMEOUT_SECONDS = 15 * 60


def prepare_database(url: str) -> None:
    """Creates the database if needed and applies the migrations."""
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        exists = connection.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
        ).scalar()
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()

    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    config.attributes["database_url"] = url
    command.upgrade(config, "head")


def ingest_corpus(
    session_factory: sessionmaker[Session],
    settings: Settings,
    embedder: Embedder,
    files: list[Path] | None = None,
) -> uuid.UUID:
    """Uploads every corpus file once and processes the queue until all of them are ready.

    Returns the evaluation user's ID. Files already uploaded (same bytes) are not uploaded again,
    so running this twice embeds nothing new.
    """
    with session_factory() as session:
        user = session.scalar(select(User).where(User.email == EVAL_EMAIL))
        if user is None:
            user = register_user(session, EVAL_EMAIL, secrets.token_urlsafe(24))
        user_id = user.id
        for path in files if files is not None else corpus_files():
            upload = validate_upload(path.name, path.read_bytes())
            uploaded = session.scalar(
                select(Document.id).where(
                    Document.owner_id == user_id, Document.sha256 == upload.sha256
                )
            )
            if uploaded is None:
                create_document(
                    session, user_id, upload, max_documents=100, request_id="evaluation"
                )
                logger.info("evaluation.uploaded", extra={"file": path.name})

    deadline = time.monotonic() + PROCESSING_TIMEOUT_SECONDS
    while True:
        while process_next_job(
            session_factory, worker_id="evaluation", embedder=embedder, settings=settings
        ):
            pass
        with session_factory() as session:
            documents = session.execute(
                select(Document.filename, Document.status, Document.error).where(
                    Document.owner_id == user_id
                )
            ).all()
        failed = [f"{name}: {error}" for name, status, error in documents if status == "failed"]
        if failed:
            raise RuntimeError("Some corpus documents could not be processed: " + "; ".join(failed))
        if all(status == "ready" for _, status, _ in documents):
            return user_id
        if time.monotonic() > deadline:
            raise RuntimeError("The corpus was not processed in time.")
        time.sleep(5)  # a job is waiting for its retry time

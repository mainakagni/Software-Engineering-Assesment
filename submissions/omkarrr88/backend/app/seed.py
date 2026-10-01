"""Creates the demo account and queues its sample documents. Safe to run on every start.

    python -m app.seed

app.supervisor runs it when SEED_DEMO is set; DEMO_USER_EMAIL and DEMO_USER_PASSWORD name the
account. A sample that is missing from the account (a visitor deleted it) is queued again, so the
shared demo account recovers on the next restart. The worker does the processing.
"""

import logging
import sys
from collections.abc import Sequence
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.auth.schemas import normalize_email
from app.auth.service import register_user
from app.config import Settings, get_settings
from app.db.models import Document, User
from app.db.session import make_session_factory
from app.documents.service import create_document
from app.documents.validation import validate_upload
from app.logging_config import configure_logging

logger = logging.getLogger("app.seed")

# The evaluation corpus doubles as the demo's sample documents; the image copies it here too.
SAMPLE_DIR = Path(__file__).resolve().parent.parent / "evaluation" / "corpus"
NOT_SAMPLES = frozenset({"ATTRIBUTION.md"})  # licence notes that live next to the documents


def sample_files(directory: Path = SAMPLE_DIR) -> list[Path]:
    return sorted(
        path for path in directory.iterdir() if path.is_file() and path.name not in NOT_SAMPLES
    )


def seed_demo(
    session_factory: sessionmaker[Session], settings: Settings, files: Sequence[Path]
) -> int:
    """Creates the account if needed and queues every sample it lacks. Returns how many."""
    if not settings.demo_user_email or not settings.demo_user_password:
        raise ValueError("DEMO_USER_EMAIL and DEMO_USER_PASSWORD must be set to seed the demo")
    email = normalize_email(settings.demo_user_email)
    queued = 0
    with session_factory() as session:
        user = session.scalar(select(User).where(User.email == email))
        if user is None:
            user = register_user(session, email, settings.demo_user_password.get_secret_value())
            logger.info("seed.user_created", extra={"user_id": str(user.id)})
        for path in files:
            upload = validate_upload(path.name, path.read_bytes())
            present = session.scalar(
                select(Document.id).where(
                    Document.owner_id == user.id, Document.sha256 == upload.sha256
                )
            )
            if present is None:
                create_document(
                    session, user.id, upload,
                    max_documents=settings.max_documents_per_user, request_id="seed",
                )  # fmt: skip
                queued += 1
    return queued


def main() -> int:
    settings = get_settings()
    configure_logging(settings.log_level)
    try:
        queued = seed_demo(make_session_factory(settings), settings, sample_files())
    except Exception:
        logger.exception("seed.failed")
        return 1
    logger.info("seed.done", extra={"documents_queued": queued})
    return 0


if __name__ == "__main__":
    sys.exit(main())

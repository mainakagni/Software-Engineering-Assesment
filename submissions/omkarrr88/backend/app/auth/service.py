"""Creating accounts and checking credentials."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth.passwords import hash_password, verify_password
from app.auth.schemas import normalize_email
from app.db.models import User
from app.errors import ConflictError, UnauthorizedError

INVALID_CREDENTIALS_MESSAGE = "Invalid email or password."


def register_user(session: Session, email: str, password: str) -> User:
    user = User(email=normalize_email(email), password_hash=hash_password(password))
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        # The unique index on email is the source of truth, so two concurrent sign-ups with the
        # same address cannot both succeed.
        session.rollback()
        raise ConflictError("An account with this email already exists.") from exc
    return user


def authenticate(session: Session, email: str, password: str) -> User:
    user = session.scalar(select(User).where(User.email == normalize_email(email)))
    if not verify_password(password, user.password_hash if user else None) or user is None:
        raise UnauthorizedError(INVALID_CREDENTIALS_MESSAGE)
    return user

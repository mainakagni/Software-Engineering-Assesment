"""Signed access tokens (JWT, HS256)."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt

from app.config import Settings
from app.errors import UnauthorizedError

ALGORITHM = "HS256"
# Marks the token as an access token, so any other kind added later cannot be used in its place.
ACCESS_TYP = "access"
SESSION_INVALID_MESSAGE = "Your session is invalid or has expired. Please log in again."


def create_access_token(
    user_id: uuid.UUID, settings: Settings, now: datetime | None = None
) -> tuple[str, int]:
    """Returns the token and how many seconds it stays valid."""
    issued_at = now or datetime.now(UTC)
    lifetime = timedelta(minutes=settings.jwt_expires_minutes)
    claims = {
        "sub": str(user_id),
        "iat": issued_at,
        "exp": issued_at + lifetime,
        "typ": ACCESS_TYP,
    }
    token = jwt.encode(claims, settings.jwt_secret.get_secret_value(), algorithm=ALGORITHM)
    return token, int(lifetime.total_seconds())


def decode_access_token(token: str, settings: Settings) -> uuid.UUID:
    """Returns the user ID from a valid token; anything else is a 401."""
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=[ALGORITHM],  # never trust the algorithm named in the token header
            options={"require": ["exp", "iat", "sub"]},
        )
        user_id = uuid.UUID(claims["sub"])
    except (jwt.PyJWTError, ValueError) as exc:
        raise UnauthorizedError(SESSION_INVALID_MESSAGE) from exc
    if claims.get("typ") != ACCESS_TYP:
        raise UnauthorizedError(SESSION_INVALID_MESSAGE)
    return user_id

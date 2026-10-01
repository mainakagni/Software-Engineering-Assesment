"""Request and response bodies for the auth endpoints."""

import re
import uuid
from datetime import datetime
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

# Deliberately loose: one @, no spaces, a dot in the domain. Proving an address works would take a
# confirmation email, which this service does not send.
_EMAIL_SHAPE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
MAX_EMAIL_LENGTH = 254


def normalize_email(value: str) -> str:
    return value.strip().lower()


def _valid_email(value: str) -> str:
    email = normalize_email(value)
    if len(email) > MAX_EMAIL_LENGTH or not _EMAIL_SHAPE.fullmatch(email):
        raise ValueError("Enter a valid email address.")
    return email


class SignupRequest(BaseModel):
    email: Annotated[str, AfterValidator(_valid_email)] = Field(examples=["you@example.com"])
    # Argon2 accepts any length; the upper bound only stops multi-megabyte "passwords".
    password: str = Field(min_length=8, max_length=128, examples=["a long passphrase"])


class LoginRequest(BaseModel):
    # No format rules here: a malformed email simply fails to log in with the usual 401.
    email: str = Field(max_length=MAX_EMAIL_LENGTH, examples=["you@example.com"])
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    created_at: datetime


class TokenOut(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 (not a secret)
    expires_in: int = Field(description="Seconds until the token expires.")
    user: UserOut


class OAuthTokenOut(BaseModel):
    """The plain OAuth2 token response, used only by /api/auth/token for Swagger's Authorize."""

    access_token: str
    token_type: Literal["bearer"] = "bearer"  # noqa: S105 (not a secret)

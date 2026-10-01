"""Password hashing with Argon2id (argon2-cffi defaults: the RFC 9106 low-memory profile)."""

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

_hasher = PasswordHasher()

# Checked when the email is unknown, so a failed login costs the same time whether or not the
# account exists and response times do not reveal which emails are registered.
_DUMMY_HASH = _hasher.hash("placeholder-password-for-timing")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """True if the password matches. With no hash (unknown user) it does the same work and fails."""
    if password_hash is None:
        _matches(_DUMMY_HASH, password)
        return False
    return _matches(password_hash, password)


def _matches(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerificationError, InvalidHashError):
        return False

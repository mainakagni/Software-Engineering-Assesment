import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.auth.passwords import hash_password, verify_password
from app.auth.schemas import SignupRequest
from app.auth.tokens import ALGORITHM, create_access_token, decode_access_token
from app.errors import UnauthorizedError
from tests.conftest import make_test_settings

SETTINGS = make_test_settings(jwt_expires_minutes=15)
SECRET = SETTINGS.jwt_secret.get_secret_value()


def test_password_hash_round_trip() -> None:
    stored = hash_password("correct horse battery")
    assert stored.startswith("$argon2id$")
    assert "correct horse battery" not in stored
    assert verify_password("correct horse battery", stored)
    assert not verify_password("wrong horse battery", stored)


@pytest.mark.parametrize("stored", [None, "", "not-a-hash", "$argon2id$v=19$broken"])
def test_missing_or_broken_hashes_never_verify(stored: str | None) -> None:
    assert not verify_password("anything at all", stored)


def test_token_round_trip() -> None:
    user_id = uuid.uuid4()
    token, expires_in = create_access_token(user_id, SETTINGS)
    assert expires_in == 15 * 60
    assert decode_access_token(token, SETTINGS) == user_id


def test_expired_token_is_rejected() -> None:
    long_ago = datetime.now(UTC) - timedelta(hours=2)
    token, _ = create_access_token(uuid.uuid4(), SETTINGS, now=long_ago)
    with pytest.raises(UnauthorizedError):
        decode_access_token(token, SETTINGS)


def test_token_signed_with_another_secret_is_rejected() -> None:
    other = make_test_settings(jwt_secret="another-secret-that-is-at-least-32-chars")
    token, _ = create_access_token(uuid.uuid4(), other)
    with pytest.raises(UnauthorizedError):
        decode_access_token(token, SETTINGS)


def _forge(claims: dict[str, object], algorithm: str = ALGORITHM, key: str = SECRET) -> str:
    return jwt.encode(claims, key, algorithm=algorithm)


@pytest.mark.parametrize(
    "claims",
    [
        {
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "typ": "access",
        },
        {"sub": str(uuid.uuid4()), "iat": datetime.now(UTC), "typ": "access"},
        {"sub": "not-a-uuid", "iat": datetime.now(UTC), "exp": datetime.now(UTC) + timedelta(5)},
        {
            "sub": str(uuid.uuid4()),
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(5),
        },
        {
            "sub": str(uuid.uuid4()),
            "iat": datetime.now(UTC),
            "exp": datetime.now(UTC) + timedelta(minutes=5),
            "typ": "refresh",
        },
    ],
    ids=["no-sub", "no-exp", "bad-sub", "no-type", "wrong-type"],
)
def test_malformed_claims_are_rejected(claims: dict[str, object]) -> None:
    with pytest.raises(UnauthorizedError):
        decode_access_token(_forge(claims), SETTINGS)


def test_unsigned_token_is_rejected() -> None:
    now = datetime.now(UTC)
    claims = {"sub": str(uuid.uuid4()), "iat": now, "exp": now + timedelta(minutes=5)}
    unsigned = jwt.encode({**claims, "typ": "access"}, "", algorithm="none")
    with pytest.raises(UnauthorizedError):
        decode_access_token(unsigned, SETTINGS)


def test_garbage_is_rejected() -> None:
    with pytest.raises(UnauthorizedError):
        decode_access_token("not.a.jwt", SETTINGS)


@pytest.mark.parametrize(
    ("given", "stored"),
    [
        ("  Alice@Example.COM ", "alice@example.com"),
        ("bob@mail.example.org", "bob@mail.example.org"),
    ],
)
def test_signup_emails_are_normalised(given: str, stored: str) -> None:
    assert SignupRequest(email=given, password="long enough").email == stored


@pytest.mark.parametrize("email", ["", "alice", "alice@", "@example.com", "a b@example.com", "a@b"])
def test_signup_rejects_malformed_emails(email: str) -> None:
    with pytest.raises(ValueError, match="valid email"):
        SignupRequest(email=email, password="long enough")

import pytest
from pydantic import ValidationError

from app.config import DEV_JWT_SECRET
from tests.conftest import make_test_settings


@pytest.mark.parametrize(
    ("given", "expected"),
    [
        ("postgres://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
        ("postgresql://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
        ("postgresql+psycopg://u:p@h:5432/d", "postgresql+psycopg://u:p@h:5432/d"),
    ],
)
def test_database_url_always_uses_psycopg(given: str, expected: str) -> None:
    assert make_test_settings(database_url=given).database_url == expected


PRODUCTION = {"app_env": "production", "jwt_secret": "x" * 40, "trust_proxy_headers": True}


def test_production_rejects_the_development_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        make_test_settings(**{**PRODUCTION, "jwt_secret": DEV_JWT_SECRET})


def test_production_rejects_a_short_jwt_secret() -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET"):
        make_test_settings(**{**PRODUCTION, "jwt_secret": "too-short"})


def test_production_must_say_whether_it_is_behind_a_proxy() -> None:
    with pytest.raises(ValidationError, match="TRUST_PROXY_HEADERS"):
        make_test_settings(**{**PRODUCTION, "trust_proxy_headers": None})
    assert (
        make_test_settings(**{**PRODUCTION, "trust_proxy_headers": False}).app_env == "production"
    )
    assert make_test_settings().trust_proxy_headers is None  # outside production: not trusted


@pytest.mark.parametrize("app_env", ["development", "production"])
def test_gemini_providers_need_a_key(app_env: str) -> None:
    with pytest.raises(ValidationError, match="GEMINI_API_KEY"):
        make_test_settings(
            **{**PRODUCTION, "app_env": app_env}, embedding_provider="gemini", gemini_api_key=None
        )


def test_production_with_fake_providers_needs_no_key() -> None:
    settings = make_test_settings(**PRODUCTION)
    assert settings.gemini_api_key is None


def test_embedding_dimension_must_match_the_schema() -> None:
    with pytest.raises(ValidationError, match="EMBEDDING_DIM"):
        make_test_settings(embedding_dim=1536)


def test_cors_origins_are_split_and_trimmed() -> None:
    settings = make_test_settings(cors_origins=" http://a.test, ,http://b.test ")
    assert settings.cors_origin_list == ["http://a.test", "http://b.test"]
    assert make_test_settings().cors_origin_list == []


def test_upload_limit_in_bytes() -> None:
    assert make_test_settings(max_upload_mb=2).max_upload_bytes == 2 * 1024 * 1024


def test_the_similarity_floor_defaults_to_the_embedding_models_own() -> None:
    assert make_test_settings(embedding_provider="fake").min_similarity == 0.35
    gemini = make_test_settings(embedding_provider="gemini", gemini_api_key="k")
    assert gemini.min_similarity == 0.60
    assert make_test_settings(retrieval_min_similarity=0.5).min_similarity == 0.5

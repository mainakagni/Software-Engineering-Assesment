"""Application settings.

Every value comes from an environment variable of the same name in upper case (``APP_ENV``,
``DATABASE_URL``, ...). A local ``.env`` file is read too, which is how docker compose and local
development pass configuration in.
"""

from functools import lru_cache
from typing import Literal, Self

from pydantic import SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Used only outside production (the validator below rejects it there). 32+ characters because
# shorter HS256 keys are considered weak.
DEV_JWT_SECRET = "dev-only-secret-never-use-in-production"  # noqa: S105
VECTOR_DIM = 768  # size of the chunks.embedding column in the database


class DatabaseSettings(BaseSettings):
    """The part of the configuration that migrations need, so they run without provider keys."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    log_level: str = "INFO"
    database_url: str = "postgresql+psycopg://documind:documind@localhost:5433/documind"

    @field_validator("database_url")
    @classmethod
    def _use_psycopg_driver(cls, url: str) -> str:
        # Hosting providers hand out postgres:// or postgresql:// URLs; SQLAlchemy needs to be
        # told to use psycopg 3, otherwise it looks for psycopg2.
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url


class Settings(DatabaseSettings):
    app_env: Literal["development", "test", "production"] = "development"

    db_pool_size: int = 5
    db_max_overflow: int = 5

    jwt_secret: SecretStr = SecretStr(DEV_JWT_SECRET)
    jwt_expires_minutes: int = 60

    gemini_api_key: SecretStr | None = None
    llm_provider: Literal["gemini", "fake"] = "gemini"
    llm_model: str = "gemini-3.5-flash-lite"
    llm_temperature: float = 0.1
    llm_max_output_tokens: int = 1024
    # Empty string sends no thinking config at all (for models that do not support it).
    llm_thinking_level: Literal["", "MINIMAL", "LOW", "MEDIUM", "HIGH"] = "LOW"
    llm_timeout_seconds: float = 20
    embedding_provider: Literal["gemini", "fake"] = "gemini"
    embedding_model: str = "gemini-embedding-001"
    embedding_dim: int = VECTOR_DIM
    embedding_timeout_seconds: float = 10
    embedding_batch_size: int = 50
    provider_max_retries: int = 2
    provider_max_retry_wait_seconds: float = 10
    # Nobody is waiting on the worker, so it can sit out a per-minute rate limit.
    worker_provider_max_retries: int = 4
    worker_provider_max_retry_wait_seconds: float = 65

    retrieval_top_k: int = 6
    retrieval_min_similarity: float = 0.35
    chunk_size_chars: int = 1400
    chunk_overlap_chars: int = 200

    max_upload_mb: int = 10
    max_documents_per_user: int = 20
    max_pdf_pages: int = 300
    max_chunks_per_document: int = 1500

    questions_per_minute: int = 10
    questions_per_day: int = 100
    global_questions_per_day: int = 200
    auth_attempts_per_minute: int = 10
    uploads_per_day: int = 20
    global_uploads_per_day: int = 200
    answer_cache_ttl_hours: int = 24

    # USD per million tokens, used only for the "estimated cost" in answers.
    llm_input_price_per_mtok: float = 0.30
    llm_output_price_per_mtok: float = 2.50
    embedding_price_per_mtok: float = 0.15

    # Whether the client IP comes from X-Forwarded-For (true behind a reverse proxy such as
    # Render's) or from the socket (false when clients connect directly). Production must say which:
    # guessing wrong either lets clients spoof their IP or puts every client behind one address.
    trust_proxy_headers: bool | None = None
    trusted_proxy_count: int = 1
    cors_origins: str = ""

    worker_poll_interval_seconds: float = 1.0
    worker_heartbeat_seconds: float = 10
    worker_stale_after_seconds: float = 30
    job_lock_timeout_minutes: int = 10
    job_max_attempts: int = 3

    seed_demo: bool = False
    demo_user_email: str | None = None
    demo_user_password: SecretStr | None = None

    static_dir: str = "app/static"

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        if self.embedding_dim != VECTOR_DIM:
            raise ValueError(f"EMBEDDING_DIM must be {VECTOR_DIM} to match the database schema")
        if self.app_env == "production":
            secret = self.jwt_secret.get_secret_value()
            if len(secret) < 32 or secret == DEV_JWT_SECRET:
                raise ValueError("JWT_SECRET must be a random string of at least 32 characters")
            if self.trust_proxy_headers is None:
                raise ValueError(
                    "TRUST_PROXY_HEADERS must be set in production: true behind a reverse proxy "
                    "(as on Render), false when clients connect to the app directly"
                )
        uses_gemini = "gemini" in (self.llm_provider, self.embedding_provider)
        if uses_gemini and not self.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY is required when LLM_PROVIDER or EMBEDDING_PROVIDER is gemini "
                "(set both to fake to run without a key)"
            )
        return self

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()

"""
Application Configuration — pydantic-settings
"""
from functools import lru_cache
from typing import List
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent
BACKEND_DIR = APP_DIR.parent
PROJECT_DIR = BACKEND_DIR.parent

ENV_FILE = PROJECT_DIR / ".env"
if not ENV_FILE.exists():
    ENV_FILE = BACKEND_DIR / ".env"


import sys
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE) if ENV_FILE.exists() else ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    environment: str = "development"
    secret_key: str = "change-me-to-a-secure-random-string-of-at-least-32-chars"
    log_level: str = "INFO"

    # Database
    database_url: str = "postgresql+asyncpg://documind:changeme@localhost:5432/documind"

    # Redis / Celery
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # JWT
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60 * 24  # 24 hours

    # Gemini
    gemini_api_key: str = ""
    gemini_embedding_model: str = "gemini-embedding-001"
    gemini_llm_model: str = "gemini-2.5-flash"

    # File upload
    max_upload_size_mb: int = 20
    allowed_extensions: List[str] = ["pdf", "txt", "md"]

    # CORS
    allowed_origins: str = "http://localhost:5173,http://localhost:3000"

    # Rate limiting
    rate_limit_questions_per_minute: int = 10

    # RAG settings
    chunk_size: int = 512
    chunk_overlap: int = 50
    top_k_chunks: int = 5

    @property
    def allowed_origins_list(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @property
    def sync_database_url(self) -> str:
        """Synchronous URL for Alembic and worker."""
        return self.database_url.replace("postgresql+asyncpg://", "postgresql://")


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

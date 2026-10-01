"""Builds the configured providers. The API keeps one per process on app.state; the worker
builds its own."""

from app.config import Settings
from app.providers.embeddings import Embedder, GeminiEmbedder
from app.providers.fakes import FakeEmbedder, FakeLLM
from app.providers.gemini import make_client
from app.providers.llm import GeminiLLM, LLMClient


def build_embedder(settings: Settings, *, for_worker: bool = False) -> Embedder:
    """The configured embedder. The worker's copy retries longer, since no request is waiting."""
    if settings.embedding_provider == "fake":
        return FakeEmbedder(settings.embedding_dim)
    if settings.gemini_api_key is None:  # Settings validation normally catches this first
        raise ValueError("GEMINI_API_KEY is not set")
    client = make_client(
        settings.gemini_api_key.get_secret_value(), settings.embedding_timeout_seconds
    )
    return GeminiEmbedder(
        client,
        model=settings.embedding_model,
        dim=settings.embedding_dim,
        batch_size=settings.embedding_batch_size,
        max_retries=(
            settings.worker_provider_max_retries if for_worker else settings.provider_max_retries
        ),
        max_wait_seconds=(
            settings.worker_provider_max_retry_wait_seconds
            if for_worker
            else settings.provider_max_retry_wait_seconds
        ),
    )


def build_llm(settings: Settings) -> LLMClient:
    if settings.llm_provider == "fake":
        return FakeLLM()
    if settings.gemini_api_key is None:  # Settings validation normally catches this first
        raise ValueError("GEMINI_API_KEY is not set")
    return GeminiLLM(
        make_client(settings.gemini_api_key.get_secret_value(), settings.llm_timeout_seconds),
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_output_tokens=settings.llm_max_output_tokens,
        thinking_level=settings.llm_thinking_level,
    )

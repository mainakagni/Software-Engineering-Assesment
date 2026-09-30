"""Text embeddings: the interface the app uses, and the Gemini implementation."""

import math
from collections.abc import Sequence
from itertools import batched
from typing import Protocol

from google import genai
from google.genai import types

from app.providers.errors import ProviderError
from app.providers.gemini import PROVIDER, translate_error
from app.providers.retry import call_with_retries


class Embedder(Protocol):
    model: str

    def embed_documents(self, texts: Sequence[str], title: str | None = None) -> list[list[float]]:
        """One unit-length vector per text, for storing."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """A unit-length vector for a search query."""
        ...


def l2_normalize(vector: Sequence[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise ProviderError(
            PROVIDER, "bad_response", "The embedding is all zeros.", retryable=False
        )
    return [value / norm for value in vector]


class GeminiEmbedder:
    def __init__(
        self,
        client: genai.Client,
        *,
        model: str,
        dim: int,
        batch_size: int,
        max_retries: int,
        max_wait_seconds: float,
    ) -> None:
        self.client = client
        self.model = model
        self.dim = dim
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.max_wait_seconds = max_wait_seconds
        # gemini-embedding-2 has no task types; gemini-embedding-001 is trained with them.
        self.supports_task_type = not model.startswith("gemini-embedding-2")

    def embed_documents(self, texts: Sequence[str], title: str | None = None) -> list[list[float]]:
        vectors: list[list[float]] = []
        for batch in batched(texts, self.batch_size):
            vectors.extend(self._embed(list(batch), "RETRIEVAL_DOCUMENT", title))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text], "RETRIEVAL_QUERY", None)[0]

    def _embed(self, texts: list[str], task_type: str, title: str | None) -> list[list[float]]:
        config = types.EmbedContentConfig(output_dimensionality=self.dim)
        if self.supports_task_type:
            config.task_type = task_type
            config.title = title if task_type == "RETRIEVAL_DOCUMENT" else None

        def call() -> types.EmbedContentResponse:
            try:
                return self.client.models.embed_content(
                    model=self.model, contents=texts, config=config
                )
            except Exception as exc:
                raise translate_error(exc) from exc

        response = call_with_retries(
            call, max_retries=self.max_retries, max_wait_seconds=self.max_wait_seconds
        )
        embeddings = response.embeddings or []
        if len(embeddings) != len(texts):
            raise ProviderError(
                PROVIDER,
                "bad_response",
                f"Expected {len(texts)} embeddings, got {len(embeddings)}.",
                retryable=True,
            )
        return [self._check(embedding.values or []) for embedding in embeddings]

    def _check(self, values: list[float]) -> list[float]:
        if len(values) != self.dim:
            raise ProviderError(
                PROVIDER,
                "bad_response",
                f"Expected {self.dim} dimensions, got {len(values)}.",
                retryable=False,
            )
        # Only the full-size output is normalised by the API; truncated vectors are not.
        return l2_normalize(values)

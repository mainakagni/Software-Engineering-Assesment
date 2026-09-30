import math
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.genai import errors

from app.providers.embeddings import GeminiEmbedder, l2_normalize
from app.providers.errors import ProviderError
from app.providers.factory import build_embedder
from app.providers.fakes import FakeEmbedder
from app.providers.gemini import translate_error
from app.providers.retry import call_with_retries
from tests.conftest import make_test_settings

# --- retries ----------------------------------------------------------------------------------


def _flaky(errors_to_raise: list[ProviderError], result: str = "ok") -> Any:
    calls = {"n": 0}

    def call() -> str:
        calls["n"] += 1
        if errors_to_raise:
            raise errors_to_raise.pop(0)
        return result

    call.calls = calls  # type: ignore[attr-defined]
    return call


def _error(retryable: bool = True, retry_after: float | None = None) -> ProviderError:
    return ProviderError(
        "test", "unavailable", "down", retryable=retryable, retry_after=retry_after
    )


def test_retries_until_success_with_growing_jittered_delays() -> None:
    sleeps: list[float] = []
    call = _flaky([_error(), _error()])
    result = call_with_retries(
        call, max_retries=2, max_wait_seconds=10, sleep=sleeps.append, rand=lambda: 1.0
    )
    assert result == "ok"
    assert sleeps == [0.5, 1.0]


def test_gives_up_after_max_retries() -> None:
    call = _flaky([_error(), _error(), _error()])
    with pytest.raises(ProviderError):
        call_with_retries(call, max_retries=2, max_wait_seconds=10, sleep=lambda _: None)
    assert call.calls["n"] == 3


def test_non_retryable_errors_are_raised_at_once() -> None:
    call = _flaky([_error(retryable=False)])
    with pytest.raises(ProviderError):
        call_with_retries(call, max_retries=5, max_wait_seconds=10, sleep=lambda _: None)
    assert call.calls["n"] == 1


def test_provider_retry_hint_is_used_unless_too_long() -> None:
    sleeps: list[float] = []
    call = _flaky([_error(retry_after=3.0)])
    call_with_retries(call, max_retries=2, max_wait_seconds=10, sleep=sleeps.append)
    assert sleeps == [3.0]

    too_long = _flaky([_error(retry_after=45.0)])
    with pytest.raises(ProviderError):
        call_with_retries(too_long, max_retries=2, max_wait_seconds=10, sleep=sleeps.append)
    assert too_long.calls["n"] == 1


# --- Gemini error translation -------------------------------------------------------------------


def _api_error(code: int, details: list[dict[str, Any]] | None = None) -> errors.APIError:
    body = {"error": {"code": code, "message": "boom", "status": "X", "details": details or []}}
    return errors.APIError(code, body)


def test_daily_quota_is_not_retryable() -> None:
    violation = {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier"}
    error = translate_error(_api_error(429, [{"violations": [violation]}]))
    assert (error.kind, error.retryable) == ("quota_exhausted", False)


def test_per_minute_rate_limit_is_retryable_with_the_suggested_delay() -> None:
    details: list[dict[str, Any]] = [
        {"violations": [{"quotaId": "GenerateRequestsPerMinutePerProjectPerModel-FreeTier"}]},
        {"@type": "type.googleapis.com/google.rpc.RetryInfo", "retryDelay": "7s"},
    ]
    error = translate_error(_api_error(429, details))
    assert (error.kind, error.retryable, error.retry_after) == ("rate_limited", True, 7.0)


@pytest.mark.parametrize(
    ("exc", "kind", "retryable"),
    [
        (_api_error(503), "unavailable", True),
        (_api_error(500), "unavailable", True),
        (_api_error(400), "bad_request", False),
        (_api_error(403), "bad_request", False),
        (httpx.ReadTimeout("slow"), "timeout", True),
        (httpx.ConnectError("refused"), "unavailable", True),
        (RuntimeError("odd"), "bad_response", False),
    ],
)
def test_error_kinds(exc: Exception, kind: str, retryable: bool) -> None:
    error = translate_error(exc)
    assert (error.kind, error.retryable) == (kind, retryable)


# --- Gemini embedder (with a stand-in client) ----------------------------------------------------


class _Models:
    def __init__(self, dim: int, fail_with: Exception | None = None) -> None:
        self.dim = dim
        self.fail_with = fail_with
        self.requests: list[dict[str, Any]] = []

    def embed_content(self, *, model: str, contents: list[str], config: Any) -> Any:
        self.requests.append({"model": model, "contents": contents, "config": config})
        if self.fail_with:
            raise self.fail_with
        values = [[3.0, 4.0] + [0.0] * (self.dim - 2) for _ in contents]
        return SimpleNamespace(embeddings=[SimpleNamespace(values=v) for v in values])


def _embedder(models: _Models, model: str = "gemini-embedding-001") -> GeminiEmbedder:
    client = SimpleNamespace(models=models)
    return GeminiEmbedder(
        client,  # type: ignore[arg-type]
        model=model,
        dim=models.dim,
        batch_size=2,
        max_retries=0,
        max_wait_seconds=1,
    )


def test_documents_are_embedded_in_batches_with_task_type_and_title() -> None:
    models = _Models(dim=8)
    vectors = _embedder(models).embed_documents(["a", "b", "c"], title="policy.pdf")
    assert len(vectors) == 3
    assert [len(r["contents"]) for r in models.requests] == [2, 1]
    config = models.requests[0]["config"]
    assert (config.task_type, config.title, config.output_dimensionality) == (
        "RETRIEVAL_DOCUMENT",
        "policy.pdf",
        8,
    )
    assert math.isclose(sum(v * v for v in vectors[0]), 1.0)  # normalised
    assert vectors[0][:2] == pytest.approx([0.6, 0.8])


def test_queries_use_the_query_task_type() -> None:
    models = _Models(dim=8)
    _embedder(models).embed_query("what?")
    config = models.requests[0]["config"]
    assert (config.task_type, config.title) == ("RETRIEVAL_QUERY", None)


def test_models_without_task_types_get_none() -> None:
    models = _Models(dim=8)
    _embedder(models, model="gemini-embedding-2").embed_documents(["a"], title="t")
    config = models.requests[0]["config"]
    assert (config.task_type, config.title) == (None, None)


def test_wrong_dimension_is_a_bad_response() -> None:
    embedder = _embedder(_Models(dim=8))
    embedder.dim = 16
    with pytest.raises(ProviderError, match="16 dimensions"):
        embedder.embed_query("x")


def test_sdk_errors_are_translated() -> None:
    embedder = _embedder(_Models(dim=8, fail_with=_api_error(400)))
    with pytest.raises(ProviderError) as caught:
        embedder.embed_query("x")
    assert caught.value.kind == "bad_request"


def test_zero_vectors_are_rejected() -> None:
    with pytest.raises(ProviderError):
        l2_normalize([0.0, 0.0])


# --- fake embedder --------------------------------------------------------------------------------


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))


def test_fake_embedder_is_deterministic_and_meaningful() -> None:
    fake = FakeEmbedder()
    policy = fake.embed_query("Hotel stays are reimbursed up to 180 dollars per night")
    assert policy == fake.embed_query("Hotel stays are reimbursed up to 180 dollars per night")
    related = fake.embed_query("What is the hotel limit per night?")
    unrelated = fake.embed_query("Quarterly revenue grew in the retail segment")
    assert _cosine(policy, related) > 0.3
    assert abs(_cosine(policy, unrelated)) < 0.2
    assert math.isclose(_cosine(policy, policy), 1.0)


# --- factory ------------------------------------------------------------------------------------


def test_factory_builds_the_configured_embedder() -> None:
    assert isinstance(build_embedder(make_test_settings()), FakeEmbedder)

    settings = make_test_settings(embedding_provider="gemini", gemini_api_key="test-key")
    api_embedder = build_embedder(settings)
    worker_embedder = build_embedder(settings, for_worker=True)
    assert isinstance(api_embedder, GeminiEmbedder) and isinstance(worker_embedder, GeminiEmbedder)
    assert api_embedder.max_wait_seconds < worker_embedder.max_wait_seconds
    assert api_embedder.max_retries < worker_embedder.max_retries

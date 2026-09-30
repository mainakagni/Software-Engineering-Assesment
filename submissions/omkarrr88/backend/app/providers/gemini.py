"""The Gemini client and the translation of its errors into ProviderError."""

import re
from typing import Any

import httpx
from google import genai
from google.genai import errors, types

from app.providers.errors import ProviderError

PROVIDER = "gemini"
_RETRY_DELAY = re.compile(r"^(\d+(?:\.\d+)?)s$")


def make_client(api_key: str, timeout_seconds: float) -> genai.Client:
    # The SDK's own retries are switched off so that every retry goes through call_with_retries,
    # where it is logged and bounded by how long the caller can wait.
    options = types.HttpOptions(
        timeout=int(timeout_seconds * 1000),  # milliseconds
        retry_options=types.HttpRetryOptions(attempts=1),
    )
    return genai.Client(api_key=api_key, http_options=options)


def translate_error(exc: Exception) -> ProviderError:
    """Maps an exception from the SDK or the HTTP layer to a ProviderError."""
    if isinstance(exc, errors.APIError):
        return _from_api_error(exc)
    if isinstance(exc, httpx.TimeoutException):
        return ProviderError(PROVIDER, "timeout", "The request timed out.", retryable=True)
    if isinstance(exc, httpx.TransportError):
        return ProviderError(PROVIDER, "unavailable", "Could not reach the API.", retryable=True)
    return ProviderError(
        PROVIDER, "bad_response", f"Unexpected error: {type(exc).__name__}", retryable=False
    )


def _from_api_error(exc: errors.APIError) -> ProviderError:
    code = exc.code
    message = exc.message or exc.status or f"HTTP {code}"
    if code == 429:
        details = _error_details(exc.details)
        if _is_daily_quota(details):
            return ProviderError(PROVIDER, "quota_exhausted", message, retryable=False)
        return ProviderError(
            PROVIDER, "rate_limited", message, retryable=True, retry_after=_retry_delay(details)
        )
    if code in (500, 502, 503, 504):
        return ProviderError(PROVIDER, "unavailable", message, retryable=True)
    return ProviderError(PROVIDER, "bad_request", message, retryable=False)


def _error_details(body: Any) -> list[dict[str, Any]]:
    if not isinstance(body, dict):
        return []
    details = body.get("error", body).get("details")
    return [d for d in details if isinstance(d, dict)] if isinstance(details, list) else []


def _is_daily_quota(details: list[dict[str, Any]]) -> bool:
    for detail in details:
        for violation in detail.get("violations") or []:
            if isinstance(violation, dict) and "PerDay" in str(violation.get("quotaId", "")):
                return True
    return False


def _retry_delay(details: list[dict[str, Any]]) -> float | None:
    for detail in details:
        match = _RETRY_DELAY.match(str(detail.get("retryDelay", "")))
        if match:
            return float(match.group(1))
    return None

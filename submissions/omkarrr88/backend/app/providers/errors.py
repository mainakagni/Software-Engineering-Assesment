"""Provider failures, reduced to what a caller needs to decide: retry, give up, or tell the user."""

from typing import Literal

ProviderErrorKind = Literal[
    "timeout", "rate_limited", "quota_exhausted", "unavailable", "bad_request", "bad_response"
]


class ProviderError(Exception):
    def __init__(
        self,
        provider: str,
        kind: ProviderErrorKind,
        message: str,
        *,
        retryable: bool,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.kind = kind
        self.message = message
        self.retryable = retryable
        self.retry_after = retry_after

    def __str__(self) -> str:
        return f"{self.provider} {self.kind}: {self.message}"

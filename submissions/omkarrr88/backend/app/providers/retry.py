"""Retries for provider calls: exponential backoff with full jitter, bounded by how long the
caller can wait."""

import logging
import random
import time
from collections.abc import Callable

from app.providers.errors import ProviderError

logger = logging.getLogger(__name__)


def call_with_retries[T](
    call: Callable[[], T],
    *,
    max_retries: int,
    max_wait_seconds: float,
    base_delay_seconds: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
    rand: Callable[[], float] = random.random,
) -> T:
    """Runs `call`, retrying retryable ProviderErrors up to `max_retries` times.

    The provider's own retry hint wins over the computed backoff. If the wait needed is longer than
    `max_wait_seconds` the error is raised at once: a request cannot sit out a long quota window.
    """
    attempt = 0
    while True:
        try:
            return call()
        except ProviderError as exc:
            if not exc.retryable or attempt >= max_retries:
                raise
            if exc.retry_after is not None:
                delay = exc.retry_after
            else:
                delay = base_delay_seconds * 2**attempt * rand()
            if delay > max_wait_seconds:
                raise
            attempt += 1
            logger.warning(
                "provider.retry",
                extra={
                    "provider": exc.provider,
                    "kind": exc.kind,
                    "attempt": attempt,
                    "delay_seconds": round(delay, 2),
                },
            )
            sleep(delay)

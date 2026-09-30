"""Rate-limit dependencies for the routes that cost money or invite brute force."""

import ipaddress
import logging
from datetime import UTC, datetime

from fastapi import Request

from app.auth.deps import CurrentUser
from app.config import Settings
from app.dependencies import SettingsDep
from app.errors import RateLimitedError
from app.ratelimit.limiter import RateLimitDecision, hit

logger = logging.getLogger(__name__)

MINUTE = 60
DAY = 24 * 60 * 60


def client_ip(request: Request, settings: Settings) -> str:
    """The caller's IP address.

    Behind a proxy the socket peer is the proxy, and the client's address is in X-Forwarded-For.
    Every proxy appends the address it received the request from, so only entries added by our
    own proxies can be trusted: counting from the right. The left-most entries are whatever the
    client chose to send and are ignored.
    """
    if settings.trust_proxy_headers:
        entries = [e.strip() for e in request.headers.get("x-forwarded-for", "").split(",")]
        entries = [e for e in entries if e]
        if len(entries) >= settings.trusted_proxy_count:
            try:
                return str(ipaddress.ip_address(entries[-settings.trusted_proxy_count]))
            except ValueError:
                logger.warning("ratelimit.bad_forwarded_for")
    return request.client.host if request.client else "unknown"


def enforce_question_limits(request: Request, user: CurrentUser, settings: SettingsDep) -> None:
    """Per-user limits per minute and per day, and a global daily cap on questions."""
    user_key = f"q:user:{user.id}"
    _enforce(
        request,
        [
            (f"{user_key}:minute", settings.questions_per_minute, MINUTE, "question_minute"),
            (f"{user_key}:day", settings.questions_per_day, DAY, "question_day"),
            ("q:global:day", settings.global_questions_per_day, DAY, "question_global"),
        ],
    )


def enforce_upload_limits(request: Request, user: CurrentUser, settings: SettingsDep) -> None:
    """Per-user and global daily limits on uploads, which bound what embedding can cost."""
    _enforce(
        request,
        [
            (f"up:user:{user.id}:day", settings.uploads_per_day, DAY, "upload_day"),
            ("up:global:day", settings.global_uploads_per_day, DAY, "upload_global"),
        ],
    )


def enforce_auth_limit(request: Request, settings: SettingsDep) -> None:
    """Limits log-in and sign-up attempts per client IP to slow down password guessing."""
    key = f"auth:ip:{client_ip(request, settings)}:minute"
    _enforce(request, [(key, settings.auth_attempts_per_minute, MINUTE, "auth")])


def _enforce(request: Request, limits: list[tuple[str, int, int, str]]) -> None:
    """Counts the request against each (key, limit, window, scope) in order.

    The first limit exceeded rejects the request, and the ones after it are not counted: a user
    hammering their own per-minute limit must not use up a daily cap that everyone shares.
    """
    now = datetime.now(UTC)
    rejected: tuple[RateLimitDecision, str] | None = None
    with request.app.state.session_factory.begin() as session:
        for key, limit, window_seconds, scope in limits:
            decision = hit(session, key, limit=limit, window_seconds=window_seconds, now=now)
            if not decision.allowed:
                rejected = (decision, scope)
                break
    if rejected is not None:
        _reject(*rejected)


def _reject(decision: RateLimitDecision, scope: str) -> None:
    wait = decision.retry_after_seconds
    messages = {
        "question_minute": f"Too many questions. Try again in {wait} seconds.",
        "question_day": f"You have reached today's limit of {decision.limit} questions. "
        f"Try again in {_hours(wait)}.",
        "question_global": "The demo has reached its question limit for today. "
        "Please try again tomorrow.",
        "upload_day": f"You have reached today's limit of {decision.limit} uploads. "
        f"Try again in {_hours(wait)}.",
        "upload_global": "The demo has reached its upload limit for today. "
        "Please try again tomorrow.",
        "auth": f"Too many attempts. Try again in {wait} seconds.",
    }
    logger.warning(
        "ratelimit.rejected", extra={"scope": scope, "limit": decision.limit, "retry_after": wait}
    )
    raise RateLimitedError(messages[scope], retry_after_seconds=wait)


def _hours(seconds: int) -> str:
    hours = max(1, round(seconds / 3600))
    return "1 hour" if hours == 1 else f"{hours} hours"

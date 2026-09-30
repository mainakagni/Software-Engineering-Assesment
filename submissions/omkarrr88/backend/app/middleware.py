"""Plain ASGI middleware: request IDs with an access log line, and security headers."""

import logging
import re
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.logging_config import request_id_var

logger = logging.getLogger("app.http")

REQUEST_ID_HEADER = "X-Request-ID"
# Container and platform probes hit this every few seconds; keep them out of the INFO log.
QUIET_PATHS = frozenset({"/health/live"})
_VALID_REQUEST_ID = re.compile(r"[A-Za-z0-9._-]{1,64}")

# The SPA is served from our own origin and never needs inline scripts or third-party assets.
CSP_APP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
    "font-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; "
    "form-action 'self'"
)
# Swagger UI and ReDoc pages load their bundles from a CDN and start with an inline script.
CSP_DOCS = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com; "
    "font-src 'self' https://fonts.gstatic.com; "
    "img-src 'self' data: https://fastapi.tiangolo.com https://cdn.redoc.ly; "
    "worker-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'"
)
# Exact paths only: a prefix match would hand the relaxed policy to any "/docs..." URL.
DOCS_PATHS = frozenset({"/docs", "/docs/oauth2-redirect", "/redoc"})


def resolve_request_id(incoming: str | None) -> str:
    """Reuse the caller's request ID when it looks safe to log, otherwise make a new one."""
    if incoming and _VALID_REQUEST_ID.fullmatch(incoming):
        return incoming
    return uuid.uuid4().hex


class RequestContextMiddleware:
    """Sets the request ID for the request, returns it as a header and logs one line per request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = resolve_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))
        # Each request runs in its own task, so this value never leaks into other requests.
        request_id_var.set(request_id)
        started = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            logger.log(
                logging.DEBUG if scope["path"] in QUIET_PATHS else logging.INFO,
                "http.request",
                extra={
                    "method": scope["method"],
                    "path": scope["path"],
                    "status": status_code,
                    "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                },
            )


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, hsts: bool = False) -> None:
        self.app = app
        self.hsts = hsts

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        csp = CSP_DOCS if scope["path"] in DOCS_PATHS else CSP_APP

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Content-Security-Policy"] = csp
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                if self.hsts:
                    headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
            await send(message)

        await self.app(scope, receive, send_with_headers)

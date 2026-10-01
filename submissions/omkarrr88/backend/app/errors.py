"""Application errors and the handlers that turn every failure into the error envelope."""

import logging
from collections.abc import Mapping
from typing import Any, cast

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.envelope import error_payload
from app.logging_config import request_id_var
from app.middleware import REQUEST_ID_HEADER

logger = logging.getLogger(__name__)


class AppError(Exception):
    """An expected failure with a stable error code and a message that is safe to show."""

    status_code = 400
    code = "bad_request"

    def __init__(self, message: str, *, headers: dict[str, str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.headers = headers or {}


class UnauthorizedError(AppError):
    status_code = 401
    code = "unauthorized"

    def __init__(self, message: str = "Authentication required.") -> None:
        super().__init__(message, headers={"WWW-Authenticate": "Bearer"})


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "payload_too_large"


class UnsupportedMediaTypeError(AppError):
    status_code = 415
    code = "unsupported_media_type"


class ValidationFailedError(AppError):
    status_code = 422
    code = "validation_error"


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"

    def __init__(self, message: str, *, retry_after_seconds: int) -> None:
        super().__init__(message, headers={"Retry-After": str(retry_after_seconds)})


class ServiceUnavailableError(AppError):
    status_code = 503

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


_HTTP_ERROR_CODES = {
    401: "unauthorized",
    404: "not_found",
    405: "method_not_allowed",
    413: "payload_too_large",
}


def _json_error(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    payload = error_payload(code, message, request_id_var.get(), details)
    return JSONResponse(status_code=status_code, content=payload, headers=headers)


async def _handle_app_error(_: Request, exc: Exception) -> JSONResponse:
    error = cast(AppError, exc)
    return _json_error(error.status_code, error.code, error.message, headers=error.headers)


async def _handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
    error = cast(RequestValidationError, exc)
    details = [
        {"field": ".".join(str(part) for part in item["loc"][1:]), "message": _field_message(item)}
        for item in error.errors()
    ]
    return _json_error(422, "validation_error", "Some fields are missing or invalid.", details)


def _field_message(item: Mapping[str, Any]) -> str:
    # Our validators raise ValueError with a message written for users; pydantic would prefix it
    # with "Value error, ".
    context = item.get("ctx") or {}
    if item["type"] == "value_error" and "error" in context:
        return str(context["error"])
    return str(item["msg"])


async def _handle_http_error(_: Request, exc: Exception) -> JSONResponse:
    error = cast(StarletteHTTPException, exc)
    code = _HTTP_ERROR_CODES.get(error.status_code, "http_error")
    message = error.detail if isinstance(error.detail, str) else "Request failed."
    return _json_error(error.status_code, code, message, headers=error.headers)


async def _handle_unexpected_error(_: Request, exc: Exception) -> JSONResponse:
    logger.error("unhandled_error", exc_info=exc)
    # Starlette calls this handler outside the request middleware, so it sets the header itself.
    return _json_error(
        500,
        "internal_error",
        "Something went wrong on our side. Please try again.",
        headers={REQUEST_ID_HEADER: request_id_var.get() or ""},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_validation_error)
    app.add_exception_handler(StarletteHTTPException, _handle_http_error)
    app.add_exception_handler(Exception, _handle_unexpected_error)

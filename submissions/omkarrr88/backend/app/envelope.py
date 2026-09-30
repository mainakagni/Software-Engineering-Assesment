"""The response envelope every JSON endpoint uses.

{"success": true,  "data": {...}, "error": null, "meta": null}
{"success": false, "data": null, "error": {"code": ..., "message": ..., "request_id": ...}}
"""

from typing import Any, Literal

from pydantic import BaseModel


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: list[dict[str, Any]] | None = None


class PageMeta(BaseModel):
    total: int
    limit: int
    offset: int


class Envelope[T](BaseModel):
    success: bool = True
    data: T | None = None
    error: ErrorBody | None = None
    meta: PageMeta | None = None


class ErrorEnvelope(BaseModel):
    """What every failed request returns; used to document error responses in OpenAPI."""

    success: Literal[False] = False
    data: None = None
    error: ErrorBody
    meta: None = None


_ERROR_DESCRIPTIONS = {
    401: "Missing, invalid or expired access token",
    404: "Not found, or it belongs to another user",
    409: "Conflicts with the current state",
    413: "File too large",
    415: "Unsupported file type",
    422: "Invalid input; `error.details` lists the fields",
    429: "Rate limit reached; see the Retry-After header",
    503: "A dependency (database or model provider) is unavailable",
}


def error_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    """OpenAPI entries for a route's error responses, all in the error envelope."""
    return {
        code: {"model": ErrorEnvelope, "description": _ERROR_DESCRIPTIONS[code]}
        for code in status_codes
    }


def ok[T](data: T, meta: PageMeta | None = None) -> Envelope[T]:
    return Envelope[T](success=True, data=data, meta=meta)


def error_payload(
    code: str,
    message: str,
    request_id: str | None,
    details: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    body = ErrorBody(code=code, message=message, request_id=request_id, details=details)
    return Envelope[None](success=False, error=body).model_dump(mode="json")

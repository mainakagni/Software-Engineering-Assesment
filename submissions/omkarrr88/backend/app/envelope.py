"""The response envelope every JSON endpoint uses.

{"success": true,  "data": {...}, "error": null, "meta": null}
{"success": false, "data": null, "error": {"code": ..., "message": ..., "request_id": ...}}
"""

from typing import Any

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

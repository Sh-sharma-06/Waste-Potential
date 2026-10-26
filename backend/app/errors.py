"""Application-wide API error handling.

Every error response has the ``{"detail": ...}`` shape (see ErrorBody in
app/schemas/common.py).

  4xx HTTPException  → passed through unchanged (routers' messages are meant
                       for the client, e.g. 422 data-contract rejections).
  5xx HTTPException  → detail replaced with a generic message; the original is
                       logged. Routers such as pathways/decision put str(exc)
                       into their 500 details, which must not reach clients.
  Unhandled errors   → 500 with the same generic message; traceback is logged.

  Validation errors  → FastAPI's default 422 body (``detail`` is a list of
                       error objects), except that non-finite floats echoed
                       back from the rejected input (NaN, ±Infinity) are
                       returned as the strings "NaN", "Infinity", "-Infinity".
                       The default handler cannot serialize them and would
                       otherwise fail with a 500.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exception_handlers import http_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.schemas.common import ErrorBody

logger = logging.getLogger("app.errors")

INTERNAL_ERROR_DETAIL = "Internal server error"


def _internal_error_response(headers: dict[str, str] | None = None) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=ErrorBody(detail=INTERNAL_ERROR_DETAIL).model_dump(),
        headers=headers,
    )


async def _http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    if exc.status_code < 500 or exc.status_code == 503:
        return await http_exception_handler(request, exc)
    # exc_info includes the chained cause (``raise HTTPException(...) from exc``).
    logger.error(
        "HTTP %s on %s %s: %s",
        exc.status_code, request.method, request.url.path, exc.detail,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorBody(detail=INTERNAL_ERROR_DETAIL).model_dump(),
        headers=getattr(exc, "headers", None),
    )


def _json_safe(value: Any) -> Any:
    """Replace non-finite floats (at any depth) with their JSON literal names."""
    if isinstance(value, float) and not math.isfinite(value):
        if math.isnan(value):
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    return value


async def _validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": _json_safe(jsonable_encoder(exc.errors()))},
    )


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(
        "Unhandled error on %s %s", request.method, request.url.path, exc_info=exc
    )
    return _internal_error_response()


def register_error_handlers(app: FastAPI) -> None:
    """Install the project's exception handlers on *app*."""
    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)

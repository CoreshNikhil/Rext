"""Uniform JSON error envelope for every error response the API returns.

Registering a handler on Starlette's base HTTPException (not FastAPI's
subclass) catches every HTTPException raised anywhere in the app —
domain/auth errors mapped in routers and FastAPI's own 404/405s — through
one code path, so there's nowhere else in the app a second error shape
could sneak in.

slowapi's RateLimitExceeded needs a *separate* explicit registration even
though it also subclasses StarletteHTTPException: SlowAPIMiddleware
intercepts it itself, before the request ever reaches Starlette's normal
exception-dispatch machinery, and looks up a handler with a plain
`app.exception_handlers.get(type(exc), default)` — an exact-type dict
lookup, not the MRO walk Starlette's own dispatcher does. Without this
second registration, rate-limit responses would silently fall back to
slowapi's own `{"error": "..."}` shape instead of this envelope.

Every response, whatever the cause, has the same three keys:
    {"detail": ..., "error_type": "conflict", "status_code": 409}
`detail` stays a plain string for HTTPExceptions (unchanged from FastAPI's
default, so existing `resp.json()["detail"]` test assertions still work)
and the structured pydantic error list for validation failures.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("backend.errors")

_ERROR_TYPES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    501: "not_implemented",
    502: "upstream_error",
}


def _error_type_for(status_code: int) -> str:
    return _ERROR_TYPES.get(status_code, "error")


def _envelope(status_code: int, detail) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": detail, "error_type": _error_type_for(status_code), "status_code": status_code},
    )


def register_error_handlers(app: FastAPI) -> None:
    async def _http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _envelope(exc.status_code, exc.detail)

    async def _validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return _envelope(422, exc.errors())

    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        # Full traceback goes server-side only — the client never learns
        # anything beyond "something went wrong on our end."
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return _envelope(500, "An unexpected error occurred.")

    app.add_exception_handler(StarletteHTTPException, _http_exception_handler)
    app.add_exception_handler(RateLimitExceeded, _http_exception_handler)
    app.add_exception_handler(RequestValidationError, _validation_exception_handler)
    app.add_exception_handler(Exception, _unhandled_exception_handler)

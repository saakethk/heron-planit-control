"""Every error response has the body `{"error": ..., "detail": ...}`."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)

ERROR_NAMES = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found",
               409: "conflict", 422: "validation_error", 429: "rate_limited"}


def install(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse({"error": ERROR_NAMES.get(exc.status_code, "error"), "detail": exc.detail},
                            status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        detail = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse({"error": "validation_error", "detail": detail}, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s", request.url.path)
        return JSONResponse({"error": "internal_error", "detail": "unexpected server error"}, status_code=500)

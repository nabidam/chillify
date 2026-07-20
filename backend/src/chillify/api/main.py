"""FastAPI application composition.

Owns middleware, error mapping, and route mounting. Configuration is validated
and the composition root is built during startup, so an invalid deployment fails
before the process serves a request.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from chillify.api.errors import ErrorResponse, error_payload
from chillify.api.routes import system
from chillify.composition import build_composition
from chillify.config import ConfigurationError, load_settings
from chillify.infrastructure.logging.setup import SERVICE_API, configure_logging, request_context

logger = logging.getLogger(__name__)

API_PREFIX: Final = "/api/v1"
REQUEST_ID_HEADER: Final = "X-Request-ID"

# Status codes documented in ARCHITECTURE section 5, mapped to stable codes.
_STATUS_CODES: Final = {
    400: ("bad_request", False),
    404: ("not_found", False),
    405: ("method_not_allowed", False),
    409: ("conflict", False),
    413: ("payload_too_large", False),
    422: ("validation_failed", False),
    423: ("mutation_locked", True),
    502: ("provider_response_invalid", True),
    503: ("dependency_unavailable", True),
    504: ("outbound_timeout", True),
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = load_settings()
    configure_logging(service=SERVICE_API, level=settings.log_level)
    logger.info(
        "starting api",
        extra={"environment": str(settings.environment), "bind_port": settings.bind_port},
    )
    composition = build_composition(settings)
    app.state.composition = composition
    try:
        yield
    finally:
        composition.dispose()
        logger.info("api stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Chillify",
        version="1.0.0",
        summary="Downloader-first local music library for one household.",
        lifespan=lifespan,
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
        responses={"default": {"model": ErrorResponse, "description": "Error envelope"}},
    )

    @app.middleware("http")
    async def assign_request_id(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        with request_context(request_id):
            response: Response = await call_next(request)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, retryable = _STATUS_CODES.get(exc.status_code, ("request_failed", False))
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                code=code,
                message=str(exc.detail),
                request_id=_request_id(request),
                retryable=retryable,
            ),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        location = [str(part) for part in first.get("loc", []) if part not in ("body", "query")]
        return JSONResponse(
            status_code=422,
            content=error_payload(
                code="validation_failed",
                message="The request contains a field that failed validation.",
                request_id=_request_id(request),
                field=".".join(location) or None,
            ),
        )

    @app.exception_handler(ConfigurationError)
    async def handle_configuration_error(request: Request, exc: ConfigurationError) -> JSONResponse:
        logger.error("configuration error", extra={"error_code": exc.code})
        return JSONResponse(
            status_code=503,
            content=error_payload(
                code=exc.code,
                message=exc.message,
                request_id=_request_id(request),
                retryable=False,
            ),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        # Logged once, here, with a traceback that never reaches the browser.
        logger.exception("unhandled request failure", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=error_payload(
                code="internal_error",
                message="The request failed unexpectedly. The server log records the detail.",
                request_id=_request_id(request),
                retryable=True,
            ),
        )

    app.include_router(system.router, prefix=API_PREFIX)
    _configure_origins(app)
    return app


def _configure_origins(app: FastAPI) -> None:
    """Add CORS only when the operator explicitly enabled direct API access.

    The default deployment is same-origin behind nginx and adds no CORS policy
    at all, so a cross-origin mutation has nothing to negotiate with.
    """
    origins = getattr(app.state, "allowed_origins", None)
    if origins is None:
        try:
            origins = load_settings().allowed_origins
        except ConfigurationError:
            # Startup will fail with the named error; do not mask it here.
            return
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(origins),
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
            allow_headers=["Content-Type", "If-Match", "Idempotency-Key", "Last-Event-ID"],
        )


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


app = create_app()

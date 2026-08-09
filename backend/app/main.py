"""FastAPI application."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging, current_request_id, get_logger
from app.core.middleware import (
    CSRFMiddleware,
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
)

configure_logging()
logger = get_logger(__name__)

DESCRIPTION = """
Analyse ancient texts, historical documents, astronomical references and traditional
prophecies.

**The rule this API is built around:** every statement carries an explicit `claim_type`,
and the distinction between evidence and interpretation is enforced in code, not left to
tone. A claim requiring a citation cannot be stored without one — it is downgraded to an
AI hypothesis instead. Confidence for AI hypotheses is capped by policy.

Call `GET /api/v1/corpus/claim-types` for the vocabulary and how to render it.

**Getting started:** `POST /api/v1/analyses` with `{"text": "..."}`. No account is
required; you will receive an `anonymous_token` which is the only way to retrieve that
analysis later. Poll the returned `poll_url` for progress.
"""

TAGS_METADATA = [
    {"name": "analyses", "description": "Submit texts and retrieve reports."},
    {"name": "uploads", "description": "PDF, DOCX, image and URL ingestion."},
    {"name": "exports", "description": "PDF, DOCX, CSV, Markdown and JSON exports."},
    {"name": "search", "description": "Semantic and keyword search."},
    {"name": "astronomy", "description": "Eclipses, phases, conjunctions and positions. Usable on its own."},
    {"name": "calendars", "description": "Conversion between twelve calendar systems."},
    {"name": "corpus", "description": "The curated reference corpus."},
    {"name": "library", "description": "Projects, collections, tags, shares, notifications."},
    {"name": "auth", "description": "Registration, sign-in and OAuth."},
    {"name": "admin", "description": "User management, monitoring and audit. Admin only."},
    {"name": "health", "description": "Liveness, readiness and version."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "app.starting",
        environment=settings.ENVIRONMENT,
        api_prefix=settings.API_V1_PREFIX,
    )

    Path(settings.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    if settings.ENVIRONMENT != "production":
        # Convenience for development only. Production schema changes go through Alembic;
        # create_all cannot express a migration and would mask drift.
        from app.db.session import create_all

        create_all()
        logger.info("app.schema_ensured")

    from app.agents.provider import provider_status

    status_payload = provider_status()
    logger.info("app.ai_provider", **status_payload)
    if status_payload["is_offline"]:
        logger.warning(
            "app.offline_mode",
            note=(
                "No ANTHROPIC_API_KEY configured. Analyses will run on the deterministic "
                "engine: extraction, calendars and astronomy work fully, interpretive "
                "sections will report as unavailable."
            ),
        )

    yield
    logger.info("app.shutting_down")


app = FastAPI(
    title=settings.APP_NAME,
    description=DESCRIPTION,
    version="1.0.0",
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    contact={"name": "Starcode", "url": "https://github.com/starcode"},
    license_info={"name": "MIT"},
)

# Middleware runs bottom-up, so this order means: trusted host is checked first, then
# CORS, then CSRF, then security headers, then request context (outermost).
app.add_middleware(RequestContextMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Analysis-Token", "X-Request-ID"],
    expose_headers=[
        "X-Request-ID",
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset",
        "Retry-After",
        "Content-Disposition",
    ],
    max_age=600,
)
if settings.trusted_hosts != ["*"]:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)


# ---- error handling ------------------------------------------------------------------


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """Turn Pydantic's nested errors into something a form can render per-field."""
    field_errors: dict[str, list[str]] = {}
    for error in exc.errors():
        location = [str(part) for part in error["loc"] if part not in ("body", "query")]
        field = ".".join(location) or "request"
        field_errors.setdefault(field, []).append(error["msg"])

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "validation_failed",
            "detail": "Some fields were not accepted.",
            "field_errors": field_errors,
            "request_id": current_request_id(),
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": _error_slug(exc.status_code),
            "detail": exc.detail,
            "request_id": current_request_id(),
        },
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("app.unhandled", path=request.url.path)
    # The message never contains the exception text: stack traces and internal messages
    # leak schema and file paths. The request id is the bridge to the full log entry.
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "internal_error",
            "detail": (
                "Something went wrong on our side. Quote the request id if you report this."
            ),
            "request_id": current_request_id(),
        },
    )


def _error_slug(status_code: int) -> str:
    return {
        400: "bad_request",
        401: "unauthenticated",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        413: "payload_too_large",
        422: "validation_failed",
        429: "rate_limited",
        503: "service_unavailable",
    }.get(status_code, "error")


app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", include_in_schema=False)
def root() -> dict:
    return {
        "name": settings.APP_NAME,
        "tagline": settings.APP_TAGLINE,
        "version": "1.0.0",
        "docs": "/docs",
        "api": settings.API_V1_PREFIX,
        "start_here": {
            "method": "POST",
            "path": f"{settings.API_V1_PREFIX}/analyses",
            "body": {"text": "Paste any ancient text, prophecy, or historical document."},
        },
    }


__all__ = ["app"]

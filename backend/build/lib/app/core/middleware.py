"""Request middleware: correlation IDs, security headers, CSRF, timing."""

from __future__ import annotations

import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.core.config import settings
from app.core.logging import bind_request_context, get_logger, new_request_id

logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assign a request id, bind logging context, time the request."""

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id") or new_request_id()
        bind_request_context(request_id=request_id, user_id=None)
        request.state.request_id = request_id

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration = (time.perf_counter() - start) * 1000
            logger.exception(
                "request.unhandled_error",
                method=request.method,
                path=request.url.path,
                duration_ms=round(duration, 2),
            )
            raise

        duration = (time.perf_counter() - start) * 1000
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Response-Time-ms"] = f"{duration:.1f}"

        for header, value in getattr(request.state, "rate_limit_headers", {}).items():
            response.headers[header] = value

        # Health checks would otherwise dominate the log at one line per second.
        if not request.url.path.startswith("/api/v1/health"):
            logger.info(
                "request.completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration, 2),
            )
        return response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Defence-in-depth headers.

    This is a JSON API, so the CSP is maximally restrictive — nothing here should ever
    load a script or be framed. The interactive docs are the one exception and are
    exempted, since Swagger UI needs its own assets.
    """

    DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)

        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=(), payment=()"
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-site")

        if not request.url.path.startswith(self.DOCS_PATHS):
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )

        if settings.ENVIRONMENT in ("production", "staging"):
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains; preload"
            )

        return response


class CSRFMiddleware(BaseHTTPMiddleware):
    """Origin-checking CSRF defence for cookie-authenticated requests.

    The API authenticates with bearer tokens, which are not sent automatically by the
    browser and so are not CSRF-able. This middleware exists for the cookie-session path
    (OAuth callbacks) and as a safety net if cookie auth is ever added: an unsafe method
    carrying a cookie must present an Origin or Referer this server recognises.
    """

    SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "TRACE"})

    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method in self.SAFE_METHODS:
            return await call_next(request)

        # Bearer-authenticated requests cannot be forged cross-site: the browser will not
        # attach an Authorization header on the attacker's behalf.
        if request.headers.get("authorization"):
            return await call_next(request)

        if not request.cookies:
            return await call_next(request)

        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        allowed = set(settings.cors_origins) | {settings.FRONTEND_BASE_URL}

        if origin:
            if origin not in allowed:
                return _forbidden(request, "Origin not permitted for a state-changing request.")
        elif referer:
            if not any(referer.startswith(candidate) for candidate in allowed):
                return _forbidden(request, "Referer not permitted for a state-changing request.")
        else:
            return _forbidden(
                request,
                "A state-changing request with cookies must include an Origin or Referer header.",
            )

        return await call_next(request)


def _forbidden(request: Request, detail: str) -> Response:
    from fastapi.responses import JSONResponse

    logger.warning(
        "csrf.blocked",
        path=request.url.path,
        origin=request.headers.get("origin"),
        referer=request.headers.get("referer"),
    )
    return JSONResponse(
        status_code=403,
        content={
            "error": "csrf_check_failed",
            "detail": detail,
            "request_id": getattr(request.state, "request_id", None),
        },
    )


__all__ = ["RequestContextMiddleware", "SecurityHeadersMiddleware", "CSRFMiddleware"]

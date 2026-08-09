"""Health and readiness."""

from __future__ import annotations

import time

from fastapi import APIRouter, Response, status
from sqlalchemy import select, text

from app.api.deps import DbSession
from app.core.config import settings
from app.schemas.common import HealthResponse

router = APIRouter(tags=["health"])

VERSION = "1.0.0"
_STARTED_AT = time.time()


@router.get("/health", response_model=HealthResponse, summary="Liveness and dependency check")
def health(response: Response, db: DbSession) -> HealthResponse:
    from app.agents.provider import provider_status

    checks: dict = {}
    overall = "ok"

    start = time.perf_counter()
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - start) * 1000, 2),
            "dialect": db.bind.dialect.name if db.bind else "unknown",
        }
    except Exception as exc:  # noqa: BLE001
        checks["database"] = {"status": "error", "error": str(exc)[:200]}
        overall = "degraded"

    try:
        from app.core.rate_limit import _RedisBackend, get_backend

        backend = get_backend()
        checks["rate_limit"] = {
            "status": "ok",
            "backend": "redis" if isinstance(backend, _RedisBackend) else "in-process",
            "note": (
                None
                if isinstance(backend, _RedisBackend)
                else "Redis is unavailable, so limits are enforced per worker rather than "
                "globally."
            ),
        }
    except Exception as exc:  # noqa: BLE001
        checks["rate_limit"] = {"status": "error", "error": str(exc)[:200]}

    try:
        from app.db.models.knowledge import KnowledgeChunk
        from sqlalchemy import func

        count = db.execute(select(func.count()).select_from(KnowledgeChunk)).scalar_one()
        checks["corpus"] = {
            "status": "ok" if count else "empty",
            "indexed_chunks": count,
            "note": None if count else "Run the seeder: python -m app.workers.seed_cli",
        }
        if not count:
            overall = "degraded" if overall == "ok" else overall
    except Exception as exc:  # noqa: BLE001
        checks["corpus"] = {"status": "error", "error": str(exc)[:200]}

    checks["uptime_seconds"] = round(time.time() - _STARTED_AT, 1)

    # 503 on a degraded check so a load balancer takes this instance out rather than
    # sending traffic to something that cannot serve it.
    if checks.get("database", {}).get("status") == "error":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        overall = "error"

    return HealthResponse(
        status=overall,
        version=VERSION,
        environment=settings.ENVIRONMENT,
        database=checks.get("database", {}).get("status", "unknown"),
        ai_provider=provider_status(),
        checks=checks,
    )


@router.get("/health/live", summary="Liveness only — no dependencies touched")
def live() -> dict:
    return {"status": "ok", "uptime_seconds": round(time.time() - _STARTED_AT, 1)}


@router.get("/health/ready", summary="Readiness — fails if the database is unreachable")
def ready(response: Response, db: DbSession) -> dict:
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as exc:  # noqa: BLE001
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "error": str(exc)[:200]}


@router.get("/version")
def version() -> dict:
    from app.agents.provider import provider_status
    from app.astronomy.service import ENGINE_NAME

    return {
        "name": settings.APP_NAME,
        "version": VERSION,
        "environment": settings.ENVIRONMENT,
        "api_prefix": settings.API_V1_PREFIX,
        "engines": {
            "astronomy": ENGINE_NAME,
            "calendars": "starcode-calendars/1.0",
            "ai": provider_status(),
        },
    }


__all__ = ["router", "VERSION"]

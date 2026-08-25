"""API v1 aggregate router."""

from fastapi import APIRouter

from app.api.v1.routers import (
    admin,
    analyses,
    auth,
    billing,
    exports,
    health,
    library,
    reference,
    search,
    uploads,
)

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(analyses.router)
api_router.include_router(billing.router)
api_router.include_router(exports.router)
api_router.include_router(uploads.router)
api_router.include_router(search.router)
api_router.include_router(library.router)
api_router.include_router(reference.router)
api_router.include_router(admin.router)

__all__ = ["api_router"]

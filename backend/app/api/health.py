"""Health / liveness endpoints.

`/health` is a dependency-free liveness probe (used by Docker healthchecks and
the acceptance test for Phase 0). `/health/ready` is a readiness probe that will
check Postgres and Redis connectivity once those are wired up in later phases.
"""

from datetime import datetime, timezone

from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/health/ready")
async def ready() -> dict:
    # Phase 0: no external dependencies are required to be ready yet.
    # Postgres/Redis checks are added when those services are introduced.
    return {
        "status": "ready",
        "checks": {
            "api": "ok",
        },
    }

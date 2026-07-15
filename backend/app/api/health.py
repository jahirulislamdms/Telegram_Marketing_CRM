"""Health / liveness / readiness endpoints.

``/health`` is a dependency-free liveness probe (used by Docker healthchecks).
``/health/ready`` is a readiness probe that checks Postgres (required) and Redis
(reported, non-fatal): the API can still serve requests without the Celery broker.
"""

import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.session import get_db

router = APIRouter(tags=["health"])
log = logging.getLogger("health")


@router.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "time": datetime.now(timezone.utc).isoformat(),
    }


async def _check_database(db: AsyncSession) -> bool:
    try:
        await db.execute(text("SELECT 1"))
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("readiness: database check failed: %s", exc)
        return False


async def _check_redis() -> bool:
    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await client.ping()
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("readiness: redis check failed: %s", exc)
        return False
    finally:
        try:
            await client.aclose()
        except Exception:  # noqa: BLE001
            pass


@router.get("/health/ready")
async def ready(response: Response, db: AsyncSession = Depends(get_db)) -> dict:
    db_ok = await _check_database(db)
    redis_ok = await _check_redis()
    # Database is required to serve; Redis is reported but non-fatal for readiness.
    ready = db_ok
    if not ready:
        response.status_code = 503
    return {
        "status": "ready" if ready else "not_ready",
        "checks": {
            "api": "ok",
            "database": "ok" if db_ok else "down",
            "redis": "ok" if redis_ok else "down",
        },
    }

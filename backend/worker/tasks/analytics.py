"""Celery task that pushes a live Dashboard snapshot over the inbox WebSocket.

Runs on Celery beat so the Dashboard stays current without client polling. The
snapshot is published as a ``dashboard`` event via the same realtime fan-out used
by the inbox (Redis pub/sub in prod, in-process fallback in dev).
"""

import asyncio
from datetime import datetime, timezone

from celery.utils.log import get_task_logger

from app.db.session import AsyncSessionLocal
from app.realtime import publish
from app.services import analytics as analytics_service
from worker.celery_app import celery_app

log = get_task_logger(__name__)


async def _broadcast() -> dict:
    async with AsyncSessionLocal() as db:
        snapshot = await analytics_service.dashboard_snapshot(db, datetime.now(timezone.utc))
    await publish({"type": "dashboard", "snapshot": snapshot})
    return {"accounts": snapshot["accounts"].get("total", 0)}


@celery_app.task(name="analytics.dashboard_tick")
def dashboard_tick() -> dict:
    """Compute and broadcast the Dashboard snapshot."""
    return asyncio.run(_broadcast())

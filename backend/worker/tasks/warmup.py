"""Celery task that drives warmup runs on a schedule (via Celery beat)."""

import asyncio
from datetime import datetime, timezone

from celery.utils.log import get_task_logger
from sqlalchemy import select

from app.db.models.proxy import Proxy
from app.db.models.warmup import WarmupRun
from app.db.session import AsyncSessionLocal
from app.services import engine_client
from app.services import warmup as warmup_service
from worker.celery_app import celery_app

log = get_task_logger(__name__)


async def _execute(db, participant, account, action) -> None:
    proxy = await db.get(Proxy, account.proxy_id) if account.proxy_id else None
    if action["type"] == "join":
        await engine_client.warmup_join(account, proxy, action["link"])
    else:
        result = await engine_client.warmup_send(
            account, proxy, action["target"], action["text"]
        )
        if not result.get("sent", True):
            raise engine_client.EngineUnavailable(
                f"warmup send failed: {result.get('error')}"
            )


async def _tick_all() -> dict:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(WarmupRun).where(WarmupRun.status == "running")
        )
        runs = list(result.scalars().all())
        total = {"runs": 0, "actions": 0, "advanced": 0, "completed": 0}
        for run in runs:
            async def execute(participant, account, action):
                await _execute(db, participant, account, action)

            summary = await warmup_service.run_tick(
                db, run, datetime.now(timezone.utc), execute
            )
            total["runs"] += 1
            total["actions"] += len(summary["actions"])
            total["advanced"] += summary["advanced"]
            total["completed"] += summary["completed"]
        return total


@celery_app.task(name="warmup.tick")
def warmup_tick() -> dict:
    """Advance every running warmup run by one tick."""
    return asyncio.run(_tick_all())

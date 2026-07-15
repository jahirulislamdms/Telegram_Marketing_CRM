"""Celery task that drives send jobs on a schedule (via Celery beat)."""

import asyncio
from datetime import datetime, timezone

from celery.utils.log import get_task_logger
from sqlalchemy import select

from app.db.models.sender import SendJob
from app.db.session import AsyncSessionLocal
from app.services import sender as sender_service
from worker.celery_app import celery_app

log = get_task_logger(__name__)


async def _tick_all() -> dict:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(SendJob).where(SendJob.status == "running"))
        jobs = list(result.scalars().all())
        total = {"jobs": 0, "sent": 0, "paused": 0}
        for job in jobs:
            executor = sender_service.build_executor(db, None)
            summary = await sender_service.run_tick(
                db, job, datetime.now(timezone.utc), executor
            )
            total["jobs"] += 1
            total["sent"] += summary["sent"]
            if summary["paused"]:
                total["paused"] += 1
        return total


@celery_app.task(name="sender.tick")
def sender_tick() -> dict:
    """Advance every running send job by one paced tick."""
    return asyncio.run(_tick_all())

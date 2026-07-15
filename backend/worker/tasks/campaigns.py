"""Celery task that drives running campaigns on a schedule (via Celery beat)."""

import asyncio
from datetime import datetime, timezone

from celery.utils.log import get_task_logger
from sqlalchemy import select

from app.db.models.campaign import Campaign
from app.db.session import AsyncSessionLocal
from app.services import campaigns as campaign_service
from worker.celery_app import celery_app

log = get_task_logger(__name__)


async def _tick_all() -> dict:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Campaign).where(Campaign.status == "running"))
        campaigns = list(result.scalars().all())
        total = {"campaigns": 0, "sent": 0, "joined": 0, "paused": 0}
        for campaign in campaigns:
            summary = await campaign_service.run_tick(
                db, campaign, datetime.now(timezone.utc), agent_id=None
            )
            total["campaigns"] += 1
            total["sent"] += summary["sent"]
            total["joined"] += summary["joined"]
            if summary["paused"]:
                total["paused"] += 1
        return total


@celery_app.task(name="campaigns.tick")
def campaigns_tick() -> dict:
    """Advance every running campaign by one paced tick."""
    return asyncio.run(_tick_all())

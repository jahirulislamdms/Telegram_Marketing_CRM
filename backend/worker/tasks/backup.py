"""Celery task that runs the scheduled auto-backup (§15.2.e).

Beat calls this hourly; the task itself decides whether a backup is due from the
UI-editable settings (on/off + every N days), so the schedule can be changed at
runtime without touching the beat config.
"""

import asyncio

from celery.utils.log import get_task_logger

from app.db.session import AsyncSessionLocal
from app.services import backup as backup_service
from worker.celery_app import celery_app

log = get_task_logger(__name__)


async def _auto() -> dict:
    async with AsyncSessionLocal() as db:
        cfg = await backup_service.get_backup_settings(db)
        if not cfg.get("enabled"):
            return {"skipped": "disabled"}
        if not backup_service.is_due(cfg):
            return {"skipped": "not due"}
        meta = await backup_service.create_backup(db, cfg.get("scope"))
        return {"created": meta["name"], "scope": meta["scope"]}


@celery_app.task(name="backup.auto_tick")
def auto_tick() -> dict:
    """Create a scheduled backup when one is due."""
    return asyncio.run(_auto())

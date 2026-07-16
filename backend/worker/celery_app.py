"""Celery application: Redis broker + result backend.

Task modules (sending, warmup, drip, campaigns, health) are added per phase under
``worker.tasks`` and auto-discovered here.
"""

from celery import Celery

from app.config import settings

celery_app = Celery(
    "telegram_crm",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)

# Periodic tasks (run by Celery beat).
celery_app.conf.beat_schedule = {
    "warmup-tick": {
        "task": "warmup.tick",
        "schedule": 300.0,  # every 5 minutes
    },
    "sender-tick": {
        "task": "sender.tick",
        "schedule": 60.0,  # every minute
    },
    "campaigns-tick": {
        "task": "campaigns.tick",
        "schedule": 60.0,  # every minute
    },
    "dashboard-tick": {
        "task": "analytics.dashboard_tick",
        "schedule": 15.0,  # push a live Dashboard snapshot every 15 seconds
    },
    "backup-auto-tick": {
        # Checks hourly; the task honors the UI-editable on/off + every-N-days
        # schedule, so changing it needs no beat restart.
        "task": "backup.auto_tick",
        "schedule": 3600.0,
    },
}

celery_app.autodiscover_tasks(["worker.tasks"])


@celery_app.task(name="worker.ping")
def ping() -> str:
    """Smoke-test task: returns 'pong'. Used to verify the broker path works."""
    return "pong"

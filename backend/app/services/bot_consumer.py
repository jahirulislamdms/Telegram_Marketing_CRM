"""Consumer for engine bot events (Redis bot:incoming/bot:start → DB → WebSocket).

Best-effort: idle if Redis is unreachable (dev uses the bot simulate endpoint).
"""

import asyncio
import json
import logging

import redis.asyncio as aioredis

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.services import bots as bot_service

log = logging.getLogger("bot_consumer")

INCOMING_CHANNEL = "bot:incoming"
START_CHANNEL = "bot:start"

_task: asyncio.Task | None = None


async def _run() -> None:
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis.ping()
    except Exception as exc:  # noqa: BLE001
        log.warning("bot consumer: Redis unavailable (%s); not consuming", exc)
        return
    pubsub = redis.pubsub()
    await pubsub.subscribe(INCOMING_CHANNEL, START_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                data = json.loads(message["data"])
            except Exception:  # noqa: BLE001
                continue
            await _handle(message["channel"], data)
    except asyncio.CancelledError:  # pragma: no cover
        raise
    finally:
        try:
            await redis.aclose()
        except Exception:  # noqa: BLE001
            pass


async def _handle(channel: str, data: dict) -> None:
    try:
        async with AsyncSessionLocal() as db:
            if channel == START_CHANNEL:
                await bot_service.upsert_subscriber(
                    db, data["bot_id"], data["telegram_user_id"],
                    data.get("name"), data.get("utm_source"),
                )
                await db.commit()
            else:
                conv, msg = await bot_service.record_incoming(
                    db, data["bot_id"], data["telegram_user_id"], data.get("name"),
                    data.get("text"), tg_message_id=data.get("tg_message_id"),
                )
                await bot_service.broadcast_message_event(db, conv, msg)
    except Exception as exc:  # noqa: BLE001
        log.warning("bot consumer: failed to handle (%s)", exc)


async def startup() -> None:
    global _task
    _task = asyncio.create_task(_run())


async def shutdown() -> None:
    global _task
    if _task is not None:
        _task.cancel()

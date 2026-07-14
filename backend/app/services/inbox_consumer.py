"""Backend consumer for engine incoming messages (Redis → DB → WebSocket).

Subscribes to ``inbox:incoming`` (published by the engine listener), persists
each message, and fans it out to the WebSocket inbox. Best-effort: if Redis is
unreachable it logs and stays idle (single-process dev uses simulate-incoming).
"""

import asyncio
import json
import logging

import redis.asyncio as aioredis

from app.config import settings
from app.db.session import AsyncSessionLocal
from app.realtime import publish
from app.services import inbox as inbox_service

log = logging.getLogger("inbox_consumer")

INCOMING_CHANNEL = "inbox:incoming"

_task: asyncio.Task | None = None


async def _run() -> None:
    redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await redis.ping()
    except Exception as exc:  # noqa: BLE001
        log.warning("inbox consumer: Redis unavailable (%s); not consuming", exc)
        return
    pubsub = redis.pubsub()
    await pubsub.subscribe(INCOMING_CHANNEL)
    log.info("inbox consumer: subscribed to %s", INCOMING_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                data = json.loads(message["data"])
            except Exception:  # noqa: BLE001
                continue
            await _handle(data)
    except asyncio.CancelledError:  # pragma: no cover
        await pubsub.unsubscribe(INCOMING_CHANNEL)
        raise
    finally:
        try:
            await redis.aclose()
        except Exception:  # noqa: BLE001
            pass


async def _handle(data: dict) -> None:
    try:
        async with AsyncSessionLocal() as db:
            conversation, msg = await inbox_service.record_incoming(
                db,
                account_id=data["account_id"],
                peer_id=data.get("peer_id"),
                peer_name=data.get("peer_name"),
                peer_username=data.get("peer_username"),
                text=data.get("text"),
                tg_message_id=data.get("tg_message_id"),
            )
            await publish(
                {
                    "type": "message",
                    "conversation": await inbox_service.conversation_dict(db, conversation),
                    "message": inbox_service.message_dict(msg),
                }
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("inbox consumer: failed to handle incoming (%s)", exc)


async def startup() -> None:
    global _task
    _task = asyncio.create_task(_run())


async def shutdown() -> None:
    global _task
    if _task is not None:
        _task.cancel()

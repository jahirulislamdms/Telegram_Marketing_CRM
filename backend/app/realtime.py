"""Realtime inbox fan-out.

WebSocket connections are held per-process; events are fanned out to all of them.
When Redis is reachable, events are published to a Redis channel and a subscriber
re-broadcasts them locally, so fan-out works across multiple API workers. Without
Redis (single-process dev) it degrades to a pure in-process broadcast.
"""

import asyncio
import json
import logging

import redis.asyncio as aioredis
from fastapi import WebSocket

from app.config import settings

log = logging.getLogger("realtime")

EVENTS_CHANNEL = "inbox:events"


class ConnectionManager:
    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)

    @property
    def count(self) -> int:
        return len(self._connections)

    async def broadcast_local(self, event: dict) -> None:
        for ws in list(self._connections):
            try:
                await ws.send_json(event)
            except Exception:  # noqa: BLE001
                self._connections.discard(ws)


manager = ConnectionManager()

_redis: aioredis.Redis | None = None
_redis_ok = False
_sub_task: asyncio.Task | None = None


async def startup() -> None:
    global _redis, _redis_ok, _sub_task
    try:
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        await _redis.ping()
        _redis_ok = True
        _sub_task = asyncio.create_task(_subscribe())
        log.info("realtime: Redis pub/sub enabled")
    except Exception as exc:  # noqa: BLE001
        _redis_ok = False
        log.warning("realtime: Redis unavailable, in-process broadcast only (%s)", exc)


async def shutdown() -> None:
    global _sub_task, _redis
    if _sub_task is not None:
        _sub_task.cancel()
    if _redis is not None:
        try:
            await _redis.aclose()
        except Exception:  # noqa: BLE001
            pass


async def _subscribe() -> None:
    assert _redis is not None
    pubsub = _redis.pubsub()
    await pubsub.subscribe(EVENTS_CHANNEL)
    try:
        async for message in pubsub.listen():
            if message.get("type") != "message":
                continue
            try:
                await manager.broadcast_local(json.loads(message["data"]))
            except Exception:  # noqa: BLE001
                pass
    except asyncio.CancelledError:  # pragma: no cover
        await pubsub.unsubscribe(EVENTS_CHANNEL)
        raise


async def publish(event: dict) -> None:
    """Fan an event out to all connected WebSocket clients (all workers)."""
    if _redis_ok and _redis is not None:
        try:
            await _redis.publish(EVENTS_CHANNEL, json.dumps(event, default=str))
            return
        except Exception as exc:  # noqa: BLE001
            log.warning("realtime: publish failed, local fallback (%s)", exc)
    await manager.broadcast_local(event)

"""Incoming-message listener: Telethon NewMessage → Redis → backend inbox.

Registered on each authorized client. Private incoming messages are published to
the ``inbox:incoming`` Redis channel; the backend consumes them, persists them,
and fans them out to the WebSocket inbox.
"""

import json
import logging

import redis.asyncio as aioredis
from telethon import events

from app.config import settings

log = logging.getLogger("engine.listener")

INCOMING_CHANNEL = "inbox:incoming"


class _Publisher:
    def __init__(self) -> None:
        self._redis: aioredis.Redis | None = None

    async def _client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
        return self._redis

    async def publish(self, event: dict) -> None:
        try:
            client = await self._client()
            await client.publish(INCOMING_CHANNEL, json.dumps(event, default=str))
        except Exception as exc:  # noqa: BLE001
            log.warning("listener publish failed: %s", exc)


publisher = _Publisher()


def _sender_name(sender) -> str | None:
    if sender is None:
        return None
    first = getattr(sender, "first_name", None) or ""
    last = getattr(sender, "last_name", None) or ""
    name = f"{first} {last}".strip()
    return name or getattr(sender, "username", None)


def register_listener(client, account_id: int) -> None:
    if getattr(client, "_inbox_listener", False):
        return

    @client.on(events.NewMessage(incoming=True))
    async def _handler(event):  # pragma: no cover - needs live Telegram
        try:
            if not event.is_private:
                return
            sender = await event.get_sender()
            await publisher.publish(
                {
                    "account_id": account_id,
                    "peer_id": getattr(sender, "id", None),
                    "peer_name": _sender_name(sender),
                    "peer_username": getattr(sender, "username", None),
                    "text": event.raw_text,
                    "tg_message_id": event.id,
                }
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("listener handler error: %s", exc)

    client._inbox_listener = True

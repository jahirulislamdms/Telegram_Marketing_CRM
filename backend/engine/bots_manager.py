"""Hosts multiple aiogram bots inside the engine process.

Each bot polls in a background task. Incoming private messages and /start events
are published to Redis (``bot:incoming`` / ``bot:start``); the backend consumer
persists them and fans them out to the bot inbox WebSocket. Send/post go through
these methods on demand.
"""

import asyncio
import json
import logging

import redis.asyncio as aioredis

from app.config import settings

log = logging.getLogger("engine.bots")

INCOMING_CHANNEL = "bot:incoming"
START_CHANNEL = "bot:start"


class BotManager:
    def __init__(self) -> None:
        self._bots: dict[int, object] = {}
        self._tasks: dict[int, asyncio.Task] = {}
        self._redis: aioredis.Redis | None = None

    async def _publish(self, channel: str, event: dict) -> None:
        try:
            if self._redis is None:
                self._redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            await self._redis.publish(channel, json.dumps(event, default=str))
        except Exception as exc:  # noqa: BLE001
            log.warning("bot publish failed: %s", exc)

    def _make_bot(self, token: str):
        from aiogram import Bot

        return Bot(token=token)

    def _register(self, bot_id: int, dp, bot) -> None:
        from aiogram import F
        from aiogram.filters import CommandStart, CommandObject
        from aiogram.types import Message

        @dp.message(CommandStart())
        async def _on_start(message: Message, command: CommandObject):  # pragma: no cover
            await self._publish(
                START_CHANNEL,
                {
                    "bot_id": bot_id,
                    "telegram_user_id": message.from_user.id,
                    "name": message.from_user.full_name,
                    "utm_source": command.args,
                },
            )
            await message.answer("Thanks for starting! We'll be in touch.")

        @dp.message(F.text)
        async def _on_text(message: Message):  # pragma: no cover
            await self._publish(
                INCOMING_CHANNEL,
                {
                    "bot_id": bot_id,
                    "telegram_user_id": message.from_user.id,
                    "name": message.from_user.full_name,
                    "text": message.text,
                    "tg_message_id": message.message_id,
                },
            )

    async def start(self, bot_id: int, token: str) -> dict:
        from aiogram import Dispatcher

        await self.stop(bot_id)
        bot = self._make_bot(token)
        me = await bot.get_me()
        dp = Dispatcher()
        self._register(bot_id, dp, bot)
        self._bots[bot_id] = bot
        self._tasks[bot_id] = asyncio.create_task(dp.start_polling(bot))
        return {"username": me.username, "name": me.full_name, "running": True}

    async def stop(self, bot_id: int) -> dict:
        task = self._tasks.pop(bot_id, None)
        if task is not None:
            task.cancel()
        bot = self._bots.pop(bot_id, None)
        if bot is not None:
            try:
                await bot.session.close()
            except Exception:  # noqa: BLE001
                pass
        return {"running": False}

    async def info(self, token: str) -> dict:
        bot = self._make_bot(token)
        try:
            me = await bot.get_me()
            return {"username": me.username, "name": me.full_name}
        finally:
            await bot.session.close()

    async def _bot_for(self, bot_id: int, token: str):
        bot = self._bots.get(bot_id)
        if bot is None:
            bot = self._make_bot(token)
        return bot

    async def send(self, bot_id: int, token: str, chat_id, text: str) -> dict:
        bot = await self._bot_for(bot_id, token)
        msg = await bot.send_message(chat_id, text)
        return {"sent": True, "tg_message_id": msg.message_id}

    async def post(self, bot_id: int, token: str, chat_id, text: str, image_url: str | None) -> dict:
        bot = await self._bot_for(bot_id, token)
        if image_url:
            msg = await bot.send_photo(chat_id, image_url, caption=text or None)
        else:
            msg = await bot.send_message(chat_id, text)
        return {"sent": True, "tg_message_id": msg.message_id}

    async def shutdown(self) -> None:
        for bot_id in list(self._tasks):
            await self.stop(bot_id)
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:  # noqa: BLE001
                pass

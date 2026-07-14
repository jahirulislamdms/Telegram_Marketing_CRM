"""Telegram Engine Service entrypoint.

Phase 0: a minimal, dependency-light heartbeat loop that connects to Redis and
publishes a liveness key. Later phases replace the body of ``run`` with the
Telethon session manager, incoming-message listener, sender, and aiogram bots.
"""

import asyncio
import logging
import signal

import redis.asyncio as redis

from app.config import settings

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [engine] %(levelname)s %(message)s",
)
log = logging.getLogger("engine")

HEARTBEAT_KEY = "engine:heartbeat"
HEARTBEAT_INTERVAL_SEC = 15


async def run() -> None:
    log.info("Telegram Engine Service starting (Phase 0 placeholder)")
    client = redis.from_url(settings.redis_url, decode_responses=True)

    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Signal handlers are not available on Windows event loops.
            pass

    try:
        # Confirm broker connectivity before entering the loop.
        await client.ping()
        log.info("Connected to Redis at %s", settings.redis_url)

        while not stop_event.is_set():
            await client.set(HEARTBEAT_KEY, "alive", ex=HEARTBEAT_INTERVAL_SEC * 3)
            log.debug("heartbeat")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=HEARTBEAT_INTERVAL_SEC)
            except asyncio.TimeoutError:
                continue
    finally:
        await client.aclose()
        log.info("Telegram Engine Service stopped")


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

"""Telegram Engine Service entrypoint.

Runs the engine's internal HTTP API (``engine.app:app``) with uvicorn. The API's
lifespan starts the Telethon SessionManager and the Redis heartbeat.
"""

import uvicorn

from app.config import settings

ENGINE_HOST = "0.0.0.0"
ENGINE_PORT = 9100


def main() -> None:
    uvicorn.run(
        "engine.app:app",
        host=ENGINE_HOST,
        port=ENGINE_PORT,
        log_level="debug" if settings.debug else "info",
    )


if __name__ == "__main__":
    main()

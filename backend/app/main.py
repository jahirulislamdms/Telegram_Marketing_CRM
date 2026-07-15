"""FastAPI application entrypoint for the Telegram Marketing CRM."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.accounts import router as accounts_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.contacts import router as contacts_router
from app.api.health import router as health_router
from app.api.inbox import inbox_ws
from app.api.inbox import router as inbox_router
from app.api.proxies import router as proxies_router
from app.api.sender import router as sender_router
from app.api.users import router as users_router
from app.api.warmup import router as warmup_router
from app.config import settings
from app import realtime
from app.services import inbox_consumer

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [api] %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info(
        "Starting %s v%s (%s)",
        settings.app_name,
        settings.app_version,
        settings.environment,
    )
    await realtime.startup()
    await inbox_consumer.startup()
    yield
    await inbox_consumer.shutdown()
    await realtime.shutdown()
    log.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    app.include_router(auth_router, prefix="/api")
    app.include_router(users_router, prefix="/api")
    app.include_router(audit_router, prefix="/api")
    app.include_router(accounts_router, prefix="/api")
    app.include_router(proxies_router, prefix="/api")
    app.include_router(warmup_router, prefix="/api")
    app.include_router(contacts_router, prefix="/api")
    app.include_router(inbox_router, prefix="/api")
    app.include_router(sender_router, prefix="/api")
    app.add_api_websocket_route("/ws/inbox", inbox_ws)
    return app


app = create_app()

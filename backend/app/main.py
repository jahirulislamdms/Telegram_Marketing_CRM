"""FastAPI application entrypoint for the Telegram Marketing CRM."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.accounts import router as accounts_router
from app.api.analytics import router as analytics_router
from app.api.audit import router as audit_router
from app.api.auth import router as auth_router
from app.api.bots import router as bots_router
from app.api.campaigns import router as campaigns_router
from app.api.contacts import router as contacts_router
from app.api.destinations import router as destinations_router
from app.api.health import router as health_router
from app.api.inbox import inbox_ws
from app.api.inbox import router as inbox_router
from app.api.proxies import router as proxies_router
from app.api.sender import router as sender_router
from app.api.users import router as users_router
from app.api.warmup import router as warmup_router
from app.config import settings
from app import realtime
from app.middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from app.ratelimit import limiter
from app.services import bot_consumer
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
    # In production, refuse to boot on insecure default secrets.
    problems = settings.insecure_production_defaults()
    if problems:
        if settings.is_production:
            for p in problems:
                log.error("insecure configuration: %s", p)
            raise RuntimeError(
                "Refusing to start in production with insecure defaults: "
                + "; ".join(problems)
            )
        for p in problems:
            log.warning("insecure default (fine for dev, fix before prod): %s", p)
    await limiter.startup()
    await realtime.startup()
    await inbox_consumer.startup()
    await bot_consumer.startup()
    yield
    await bot_consumer.shutdown()
    await inbox_consumer.shutdown()
    await realtime.shutdown()
    await limiter.shutdown()
    log.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        lifespan=lifespan,
    )

    # Middleware runs outermost-first in reverse registration order, so register
    # the security-header and rate-limit layers before CORS: CORS ends up
    # outermost and stamps its headers onto 429/other responses too.
    app.add_middleware(SecurityHeadersMiddleware)
    app.add_middleware(RateLimitMiddleware)
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
    app.include_router(destinations_router, prefix="/api")
    app.include_router(campaigns_router, prefix="/api")
    app.include_router(bots_router, prefix="/api")
    app.include_router(analytics_router, prefix="/api")
    app.add_api_websocket_route("/ws/inbox", inbox_ws)
    return app


app = create_app()

"""Shared pytest fixtures.

The application normally talks to PostgreSQL, but for fast, dependency-free tests
we back the ORM with a temporary SQLite database and override the ``get_db``
dependency. The schema is created from the models and an admin user is seeded.
"""

import asyncio
import pathlib
import tempfile

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

import app.realtime as _realtime
import app.ratelimit as _ratelimit
import app.services.bot_consumer as _bot_consumer
import app.services.inbox_consumer as _inbox_consumer
from app.db.models import Base
from app.db.models.constants import UserRole
from app.db.session import get_db
from app.main import app
from app.services import users as user_service


# Disable the Redis-backed realtime startup during tests: the in-process
# WebSocket broadcast (publish() local fallback) still works, and this avoids a
# slow DNS timeout for the unreachable "redis" host on every TestClient lifespan.
async def _noop_async() -> None:
    return None


_realtime.startup = _noop_async
_realtime.shutdown = _noop_async
_inbox_consumer.startup = _noop_async
_inbox_consumer.shutdown = _noop_async
_bot_consumer.startup = _noop_async
_bot_consumer.shutdown = _noop_async
# Rate limiter: skip the Redis probe so it uses the in-process store in tests.
_ratelimit.limiter.startup = _noop_async
_ratelimit.limiter.shutdown = _noop_async

# Rate limiting is disabled by default in the suite (every request shares the
# TestClient's single client IP, which would trip the limit). The dedicated
# hardening test re-enables it locally via monkeypatch.
from app.config import settings as _settings  # noqa: E402

_settings.rate_limit_enabled = False

DB_PATH = pathlib.Path(tempfile.gettempdir()) / "tgcrm_test.db"
TEST_DATABASE_URL = f"sqlite+aiosqlite:///{DB_PATH.as_posix()}"

# NullPool: each session opens its own short-lived connection, so sessions used
# across different event loops (the seed loop vs. TestClient's loop) don't clash.
test_engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
TestSessionLocal = async_sessionmaker(
    test_engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)

ADMIN_EMAIL = "admin@test.com"
ADMIN_PASSWORD = "AdminPass123"


async def _init_db() -> None:
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    async with TestSessionLocal() as db:
        await user_service.create_user(
            db,
            email=ADMIN_EMAIL,
            password=ADMIN_PASSWORD,
            full_name="Seed Admin",
            role=UserRole.admin.value,
        )


async def _override_get_db():
    async with TestSessionLocal() as session:
        yield session


@pytest.fixture(scope="session", autouse=True)
def _setup_database():
    if DB_PATH.exists():
        DB_PATH.unlink()
    asyncio.run(_init_db())
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()
    asyncio.run(test_engine.dispose())
    if DB_PATH.exists():
        try:
            DB_PATH.unlink()
        except OSError:
            pass


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def admin_credentials() -> dict:
    return {"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}

"""Internal HTTP API for the Telegram Engine Service.

This API is reachable only on the private Docker network (never through Caddy).
The backend calls it to drive account login and status; all Telethon work lives
here so that sessions have a single owner.
"""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI, HTTPException

from app.config import settings
from engine.manager import EngineLoginError, SessionManager
from engine.schemas import (
    Credentials,
    JoinRequest,
    PasswordSubmit,
    PhoneSendCode,
    PhoneSignIn,
    ResolvePhone,
    ResolveUsername,
    SendRequest,
    SessionImport,
)

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [engine] %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("engine")

HEARTBEAT_KEY = "engine:heartbeat"
HEARTBEAT_INTERVAL_SEC = 15


async def _heartbeat(manager: SessionManager) -> None:
    client = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        while True:
            try:
                await client.set(
                    HEARTBEAT_KEY, "alive", ex=HEARTBEAT_INTERVAL_SEC * 3
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("heartbeat write failed: %s", exc)
            await asyncio.sleep(HEARTBEAT_INTERVAL_SEC)
    finally:
        await client.aclose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Telegram Engine Service starting")
    manager = SessionManager(settings.sessions_dir)
    app.state.manager = manager
    hb = asyncio.create_task(_heartbeat(manager))
    try:
        yield
    finally:
        hb.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await hb
        await manager.shutdown()
        log.info("Telegram Engine Service stopped")


app = FastAPI(title="Telegram Engine", lifespan=lifespan)


def _manager() -> SessionManager:
    return app.state.manager


def _proxy(cred) -> dict | None:
    return cred.proxy.model_dump() if cred.proxy else None


@app.get("/health")
async def health() -> dict:
    mgr = _manager()
    return {"status": "ok", "connected_accounts": len(mgr.clients)}


@app.post("/clients/{account_id}/start")
async def start(account_id: int, cred: Credentials) -> dict:
    try:
        return await _manager().start_client(
            account_id, cred.api_id, cred.api_hash, _proxy(cred)
        )
    except EngineLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/clients/{account_id}/status")
async def status(account_id: int) -> dict:
    return await _manager().status(account_id)


@app.post("/clients/{account_id}/logout")
async def logout(account_id: int) -> dict:
    return await _manager().logout(account_id)


@app.post("/clients/{account_id}/login/qr")
async def qr_start(account_id: int, cred: Credentials) -> dict:
    try:
        return await _manager().qr_start(
            account_id, cred.api_id, cred.api_hash, _proxy(cred)
        )
    except EngineLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.get("/clients/{account_id}/login/qr")
async def qr_status(account_id: int) -> dict:
    return await _manager().qr_status(account_id)


@app.post("/clients/{account_id}/login/qr/password")
async def qr_password(account_id: int, body: PasswordSubmit) -> dict:
    try:
        return await _manager().qr_submit_password(account_id, body.password)
    except EngineLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/clients/{account_id}/login/phone/send-code")
async def phone_send_code(account_id: int, body: PhoneSendCode) -> dict:
    try:
        return await _manager().phone_send_code(
            account_id, body.api_id, body.api_hash, _proxy(body), body.phone
        )
    except EngineLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/clients/{account_id}/login/phone/sign-in")
async def phone_sign_in(account_id: int, body: PhoneSignIn) -> dict:
    try:
        return await _manager().phone_sign_in(
            account_id, body.phone, body.code, body.phone_code_hash, body.password
        )
    except EngineLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/clients/{account_id}/login/session")
async def import_session(account_id: int, body: SessionImport) -> dict:
    try:
        return await _manager().import_session(
            account_id, body.api_id, body.api_hash, _proxy(body), body.session_string
        )
    except EngineLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ------------------------------------------------------------------ health ---


@app.post("/clients/{account_id}/health/spam-check")
async def spam_check(account_id: int, cred: Credentials) -> dict:
    try:
        return await _manager().spam_check(
            account_id, cred.api_id, cred.api_hash, _proxy(cred)
        )
    except EngineLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/clients/{account_id}/health/ban-check")
async def ban_check(account_id: int, cred: Credentials) -> dict:
    try:
        return await _manager().ban_check(
            account_id, cred.api_id, cred.api_hash, _proxy(cred)
        )
    except EngineLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/clients/{account_id}/health/unspam")
async def unspam(account_id: int, cred: Credentials) -> dict:
    try:
        return await _manager().request_unspam(
            account_id, cred.api_id, cred.api_hash, _proxy(cred)
        )
    except EngineLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/clients/{account_id}/health/unfreeze")
async def unfreeze(account_id: int, cred: Credentials) -> dict:
    try:
        return await _manager().request_unfreeze(
            account_id, cred.api_id, cred.api_hash, _proxy(cred)
        )
    except EngineLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# ------------------------------------------------------------- warmup ---------


@app.post("/clients/{account_id}/warmup/join")
async def warmup_join(account_id: int, body: JoinRequest) -> dict:
    try:
        return await _manager().join_chat(
            account_id, body.api_id, body.api_hash, _proxy(body), body.link
        )
    except EngineLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/clients/{account_id}/warmup/send")
async def warmup_send(account_id: int, body: SendRequest) -> dict:
    try:
        return await _manager().send_dm(
            account_id, body.api_id, body.api_hash, _proxy(body), body.target, body.text
        )
    except EngineLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


# --------------------------------------------------- messaging & resolve ------


@app.post("/clients/{account_id}/message")
async def send_message(account_id: int, body: SendRequest) -> dict:
    try:
        return await _manager().send_dm(
            account_id, body.api_id, body.api_hash, _proxy(body), body.target, body.text
        )
    except EngineLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/clients/{account_id}/resolve/username")
async def resolve_username(account_id: int, body: ResolveUsername) -> dict:
    try:
        return await _manager().resolve_username(
            account_id, body.api_id, body.api_hash, _proxy(body), body.username
        )
    except EngineLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@app.post("/clients/{account_id}/resolve/phone")
async def resolve_phone(account_id: int, body: ResolvePhone) -> dict:
    try:
        return await _manager().resolve_phone(
            account_id, body.api_id, body.api_hash, _proxy(body), body.phone
        )
    except EngineLoginError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

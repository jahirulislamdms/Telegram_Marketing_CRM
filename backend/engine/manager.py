"""Telethon session manager — the only place Telethon clients are created.

Owns one client per account (persisted as a file session under ``sessions_dir``)
and drives the interactive login flows: QR, phone-code, and session-string import.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import SQLiteSession, StringSession

from engine import actions as action_ops
from engine import health as health_ops
from engine import resolve as resolve_ops
from engine.proxy import to_telethon_proxy

log = logging.getLogger("engine.manager")


class EngineLoginError(Exception):
    """A login step failed for a reason the caller should see (400-class)."""


def _user_to_dict(user: Any) -> dict | None:
    if user is None:
        return None
    return {
        "id": getattr(user, "id", None),
        "username": getattr(user, "username", None),
        "first_name": getattr(user, "first_name", None),
        "last_name": getattr(user, "last_name", None),
        "phone": getattr(user, "phone", None),
    }


class _QrState:
    def __init__(self, client: TelegramClient, qr: Any):
        self.client = client
        self.qr = qr
        self.status = "waiting"  # waiting|password_needed|authorized|expired|error
        self.user: Any = None
        self.detail: str | None = None
        self.task: asyncio.Task | None = None


class SessionManager:
    def __init__(self, sessions_dir: str):
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.clients: dict[int, TelegramClient] = {}
        self.qr_logins: dict[int, _QrState] = {}
        self.phone_logins: dict[int, TelegramClient] = {}
        self._locks: dict[int, asyncio.Lock] = {}

    # -------------------------------------------------------------- helpers ---

    def _lock(self, account_id: int) -> asyncio.Lock:
        return self._locks.setdefault(account_id, asyncio.Lock())

    def _session_base(self, account_id: int) -> str:
        # Telethon appends ".session" to the name.
        return str(self.sessions_dir / str(account_id))

    def _build_client(
        self, account_id: int, api_id: str, api_hash: str, proxy: dict | None
    ) -> TelegramClient:
        if not api_id or not api_hash:
            raise EngineLoginError("API ID/HASH is not configured for this account")
        try:
            api_id_int = int(api_id)
        except ValueError:
            raise EngineLoginError("API ID must be numeric")
        return TelegramClient(
            self._session_base(account_id),
            api_id_int,
            api_hash,
            proxy=to_telethon_proxy(proxy),
        )

    async def _connected_client(
        self, account_id: int, api_id: str, api_hash: str, proxy: dict | None
    ) -> TelegramClient:
        client = self.clients.get(account_id)
        if client is None:
            client = self._build_client(account_id, api_id, api_hash, proxy)
        if not client.is_connected():
            await client.connect()
        self.clients[account_id] = client
        # Register the incoming-message listener once the client is live.
        if await client.is_user_authorized():
            from engine.listener import register_listener

            register_listener(client, account_id)
        return client

    # ----------------------------------------------------------- lifecycle ---

    async def start_client(
        self, account_id: int, api_id: str, api_hash: str, proxy: dict | None
    ) -> dict:
        """Ensure a client exists and is connected; report authorization."""
        async with self._lock(account_id):
            client = await self._connected_client(account_id, api_id, api_hash, proxy)
            authorized = await client.is_user_authorized()
            user = await client.get_me() if authorized else None
            return {
                "connected": client.is_connected(),
                "authorized": authorized,
                "user": _user_to_dict(user),
            }

    async def status(self, account_id: int) -> dict:
        client = self.clients.get(account_id)
        if client is None:
            return {"connected": False, "authorized": False, "user": None}
        authorized = client.is_connected() and await client.is_user_authorized()
        user = await client.get_me() if authorized else None
        return {
            "connected": client.is_connected(),
            "authorized": authorized,
            "user": _user_to_dict(user),
        }

    async def logout(self, account_id: int) -> dict:
        async with self._lock(account_id):
            client = self.clients.pop(account_id, None)
            self.phone_logins.pop(account_id, None)
            await self._discard_qr(account_id)
            if client is not None:
                try:
                    if not client.is_connected():
                        await client.connect()
                    await client.log_out()
                except Exception as exc:  # noqa: BLE001
                    log.warning("logout for %s failed: %s", account_id, exc)
            # Remove the persisted session file if it remains.
            session_file = Path(self._session_base(account_id) + ".session")
            if session_file.exists():
                session_file.unlink(missing_ok=True)
            return {"status": "logged_out"}

    async def shutdown(self) -> None:
        for account_id, client in list(self.clients.items()):
            try:
                await client.disconnect()
            except Exception:  # noqa: BLE001
                pass
            self.clients.pop(account_id, None)

    # ------------------------------------------------------------ QR login ---

    async def _discard_qr(self, account_id: int) -> None:
        state = self.qr_logins.pop(account_id, None)
        if state and state.task and not state.task.done():
            state.task.cancel()

    async def qr_start(
        self, account_id: int, api_id: str, api_hash: str, proxy: dict | None
    ) -> dict:
        async with self._lock(account_id):
            await self._discard_qr(account_id)
            client = await self._connected_client(account_id, api_id, api_hash, proxy)
            qr = await client.qr_login()
            state = _QrState(client, qr)
            state.task = asyncio.create_task(self._watch_qr(account_id, state))
            self.qr_logins[account_id] = state
            return {"url": qr.url, "expires_at": None}

    async def _watch_qr(self, account_id: int, state: _QrState) -> None:
        try:
            while state.status == "waiting":
                try:
                    user = await state.qr.wait(timeout=25)
                    state.user = user
                    state.status = "authorized"
                except asyncio.TimeoutError:
                    try:
                        await state.qr.recreate()
                    except Exception as exc:  # noqa: BLE001
                        state.status = "expired"
                        state.detail = str(exc)
                except SessionPasswordNeededError:
                    state.status = "password_needed"
        except asyncio.CancelledError:  # pragma: no cover
            raise
        except Exception as exc:  # noqa: BLE001
            state.status = "error"
            state.detail = str(exc)

    async def qr_status(self, account_id: int) -> dict:
        state = self.qr_logins.get(account_id)
        if state is None:
            return {"status": "expired", "detail": "no active QR login"}
        return {
            "status": state.status,
            "url": state.qr.url if state.status == "waiting" else None,
            "user": _user_to_dict(state.user),
            "detail": state.detail,
        }

    async def qr_submit_password(self, account_id: int, password: str) -> dict:
        state = self.qr_logins.get(account_id)
        if state is None:
            raise EngineLoginError("no active QR login")
        async with self._lock(account_id):
            try:
                user = await state.client.sign_in(password=password)
            except Exception as exc:  # noqa: BLE001
                return {"status": "error", "detail": str(exc)}
            state.user = user
            state.status = "authorized"
            return {"status": "authorized", "user": _user_to_dict(user)}

    # --------------------------------------------------------- phone login ---

    async def phone_send_code(
        self,
        account_id: int,
        api_id: str,
        api_hash: str,
        proxy: dict | None,
        phone: str,
    ) -> dict:
        async with self._lock(account_id):
            client = await self._connected_client(account_id, api_id, api_hash, proxy)
            sent = await client.send_code_request(phone)
            self.phone_logins[account_id] = client
            return {"phone_code_hash": sent.phone_code_hash}

    async def phone_sign_in(
        self,
        account_id: int,
        phone: str,
        code: str,
        phone_code_hash: str,
        password: str | None,
    ) -> dict:
        client = self.phone_logins.get(account_id) or self.clients.get(account_id)
        if client is None:
            raise EngineLoginError("no pending phone login; request a code first")
        async with self._lock(account_id):
            try:
                user = await client.sign_in(
                    phone=phone, code=code, phone_code_hash=phone_code_hash
                )
            except SessionPasswordNeededError:
                if not password:
                    return {"status": "password_needed"}
                user = await client.sign_in(password=password)
            except Exception as exc:  # noqa: BLE001
                return {"status": "error", "detail": str(exc)}
            self.clients[account_id] = client
            self.phone_logins.pop(account_id, None)
            return {"status": "authorized", "user": _user_to_dict(user)}

    # -------------------------------------------------------------- health ---

    async def _authorized_client(
        self, account_id: int, api_id: str, api_hash: str, proxy: dict | None
    ) -> TelegramClient:
        client = await self._connected_client(account_id, api_id, api_hash, proxy)
        if not await client.is_user_authorized():
            raise EngineLoginError("account is not logged in")
        return client

    async def spam_check(
        self, account_id: int, api_id: str, api_hash: str, proxy: dict | None
    ) -> dict:
        async with self._lock(account_id):
            client = await self._authorized_client(account_id, api_id, api_hash, proxy)
            return await health_ops.spam_check(client)

    async def ban_check(
        self, account_id: int, api_id: str, api_hash: str, proxy: dict | None
    ) -> dict:
        async with self._lock(account_id):
            # Ban-check must work even when the account is no longer authorized.
            client = await self._connected_client(account_id, api_id, api_hash, proxy)
            return await health_ops.ban_check(client)

    async def request_unspam(
        self, account_id: int, api_id: str, api_hash: str, proxy: dict | None
    ) -> dict:
        async with self._lock(account_id):
            client = await self._authorized_client(account_id, api_id, api_hash, proxy)
            return await health_ops.request_unspam(client)

    async def request_unfreeze(
        self, account_id: int, api_id: str, api_hash: str, proxy: dict | None
    ) -> dict:
        async with self._lock(account_id):
            client = await self._authorized_client(account_id, api_id, api_hash, proxy)
            return await health_ops.request_unfreeze(client)

    # -------------------------------------------------------------- actions ---

    async def join_chat(
        self, account_id: int, api_id: str, api_hash: str, proxy: dict | None, link: str
    ) -> dict:
        async with self._lock(account_id):
            client = await self._authorized_client(account_id, api_id, api_hash, proxy)
            return await action_ops.join_chat(client, link)

    async def send_dm(
        self,
        account_id: int,
        api_id: str,
        api_hash: str,
        proxy: dict | None,
        target: str,
        text: str,
    ) -> dict:
        async with self._lock(account_id):
            client = await self._authorized_client(account_id, api_id, api_hash, proxy)
            return await action_ops.send_dm(client, target, text)

    async def send_file(
        self,
        account_id: int,
        api_id: str,
        api_hash: str,
        proxy: dict | None,
        target: str,
        file: str,
        caption: str | None,
    ) -> dict:
        async with self._lock(account_id):
            client = await self._authorized_client(account_id, api_id, api_hash, proxy)
            return await action_ops.send_file(client, target, file, caption)

    async def send_media(
        self,
        account_id: int,
        api_id: str,
        api_hash: str,
        proxy: dict | None,
        target,
        data: bytes,
        filename: str | None,
        mime: str | None,
        kind: str,
        caption: str | None,
    ) -> dict:
        async with self._lock(account_id):
            client = await self._authorized_client(account_id, api_id, api_hash, proxy)
            return await action_ops.send_media(
                client, target, data, filename, mime, kind, caption
            )

    async def download_media(
        self,
        account_id: int,
        api_id: str,
        api_hash: str,
        proxy: dict | None,
        peer,
        message_id: int,
    ) -> dict | None:
        async with self._lock(account_id):
            client = await self._authorized_client(account_id, api_id, api_hash, proxy)
            return await action_ops.download_media(client, peer, message_id)

    # --------------------------------------------------------- destinations ---

    async def resolve_destination(
        self, account_id: int, api_id: str, api_hash: str, proxy: dict | None, link: str
    ) -> dict:
        async with self._lock(account_id):
            client = await self._authorized_client(account_id, api_id, api_hash, proxy)
            return await action_ops.resolve_destination(client, link)

    async def add_member(
        self,
        account_id: int,
        api_id: str,
        api_hash: str,
        proxy: dict | None,
        entity_id: int,
        target: str,
    ) -> dict:
        async with self._lock(account_id):
            client = await self._authorized_client(account_id, api_id, api_hash, proxy)
            return await action_ops.add_member(client, entity_id, target)

    # ------------------------------------------------------------- resolve ---

    async def resolve_username(
        self, account_id: int, api_id: str, api_hash: str, proxy: dict | None, username: str
    ) -> dict:
        async with self._lock(account_id):
            client = await self._authorized_client(account_id, api_id, api_hash, proxy)
            return await resolve_ops.resolve_username(client, username)

    async def resolve_phone(
        self, account_id: int, api_id: str, api_hash: str, proxy: dict | None, phone: str
    ) -> dict:
        async with self._lock(account_id):
            client = await self._authorized_client(account_id, api_id, api_hash, proxy)
            return await resolve_ops.resolve_phone(client, phone)

    # ------------------------------------------------------ session import ---

    async def import_session(
        self,
        account_id: int,
        api_id: str,
        api_hash: str,
        proxy: dict | None,
        session_string: str,
    ) -> dict:
        async with self._lock(account_id):
            try:
                string_session = StringSession(session_string)
            except Exception as exc:  # noqa: BLE001
                raise EngineLoginError(f"invalid session string: {exc}")

            # Copy the auth key into a persistent file session.
            file_session = SQLiteSession(self._session_base(account_id))
            file_session.set_dc(
                string_session.dc_id,
                string_session.server_address,
                string_session.port,
            )
            file_session.auth_key = string_session.auth_key
            file_session.save()

            client = self._build_client(account_id, api_id, api_hash, proxy)
            client.session = file_session
            await client.connect()
            if not await client.is_user_authorized():
                await client.disconnect()
                return {"status": "error", "detail": "session string is not authorized"}
            user = await client.get_me()
            self.clients[account_id] = client
            return {"status": "authorized", "user": _user_to_dict(user)}

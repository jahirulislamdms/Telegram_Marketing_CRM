"""Resolve a username or phone number to a Telegram user id (via Telethon)."""

import logging

from telethon.errors import (
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.types import InputPhoneContact

log = logging.getLogger("engine.resolve")


async def resolve_username(client, username: str) -> dict:
    handle = username.lstrip("@").strip()
    try:
        entity = await client.get_entity(handle)
    except (UsernameNotOccupiedError, UsernameInvalidError, ValueError):
        return {"user_id": None, "status": "no_telegram"}
    except Exception as exc:  # noqa: BLE001
        log.warning("resolve_username(%s) failed: %s", handle, exc)
        return {"user_id": None, "status": "failed"}
    return {"user_id": getattr(entity, "id", None), "status": "resolved"}


async def resolve_phone(client, phone: str) -> dict:
    contact = InputPhoneContact(client_id=0, phone=phone, first_name="Lead", last_name="")
    try:
        result = await client(ImportContactsRequest([contact]))
    except Exception as exc:  # noqa: BLE001
        log.warning("resolve_phone(%s) failed: %s", phone, exc)
        return {"user_id": None, "status": "failed"}
    if result.users:
        return {"user_id": result.users[0].id, "status": "resolved"}
    return {"user_id": None, "status": "no_telegram"}

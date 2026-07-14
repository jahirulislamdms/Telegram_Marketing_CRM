"""Account health operations run inside the engine (via @SpamBot and Telethon).

The reply classifier is pure and unit-tested; the Telethon interactions are
best-effort and require a live, authorized account.
"""

import asyncio
import logging
from typing import Any

from telethon.errors import (
    UserDeactivatedBanError,
    UserDeactivatedError,
)

log = logging.getLogger("engine.health")

SPAMBOT = "SpamBot"  # @SpamBot

# Spam states we normalise @SpamBot replies into.
SPAM_CLEAN = "clean"
SPAM_LIMITED = "limited"
SPAM_BANNED = "banned"
SPAM_UNKNOWN = "unknown"


def classify_spambot_reply(text: str) -> str:
    """Classify an @SpamBot reply into clean / limited / banned / unknown."""
    if not text:
        return SPAM_UNKNOWN
    t = text.lower()
    if "no limits are currently applied" in t or "free as a bird" in t:
        return SPAM_CLEAN
    if ("blocked" in t or "deleted" in t) and "terms of service" in t:
        return SPAM_BANNED
    if (
        "limited" in t
        or "flagged your" in t
        or "restrictions" in t
        or "some telegram features are unavailable" in t
    ):
        return SPAM_LIMITED
    return SPAM_UNKNOWN


def _user_to_dict(user: Any) -> dict | None:
    if user is None:
        return None
    return {
        "id": getattr(user, "id", None),
        "username": getattr(user, "username", None),
        "first_name": getattr(user, "first_name", None),
        "phone": getattr(user, "phone", None),
    }


async def _spambot_start(client) -> Any:
    """Send /start to @SpamBot and return the first response message object."""
    async with client.conversation(SPAMBOT, timeout=30) as conv:
        await conv.send_message("/start")
        return await conv.get_response()


async def spam_check(client) -> dict:
    """Ask @SpamBot for the account's spam status."""
    try:
        resp = await _spambot_start(client)
        reply = resp.message or ""
    except Exception as exc:  # noqa: BLE001
        log.warning("spam_check failed: %s", exc)
        return {"spam_state": SPAM_UNKNOWN, "reply": None, "detail": str(exc)}
    return {"spam_state": classify_spambot_reply(reply), "reply": reply}


async def ban_check(client) -> dict:
    """Determine whether the account is banned / deactivated / unauthorized."""
    try:
        if not await client.is_user_authorized():
            return {"state": "unauthorized", "user": None}
        me = await client.get_me()
        if me is None:
            return {"state": "unauthorized", "user": None}
        return {"state": "ok", "user": _user_to_dict(me)}
    except (UserDeactivatedBanError, UserDeactivatedError):
        return {"state": "banned", "user": None}
    except Exception as exc:  # noqa: BLE001
        log.warning("ban_check failed: %s", exc)
        return {"state": "error", "user": None, "detail": str(exc)}


async def request_unspam(client) -> dict:
    """Best-effort appeal to @SpamBot to lift a limit.

    @SpamBot's dispute flow uses inline buttons that change over time; this clicks
    through the first option and returns whatever it replies. Manual follow-up may
    still be required.
    """
    try:
        async with client.conversation(SPAMBOT, timeout=30) as conv:
            await conv.send_message("/start")
            resp = await conv.get_response()
            try:
                await resp.click(0)
                follow = await asyncio.wait_for(conv.get_response(), timeout=15)
                return {"submitted": True, "reply": follow.message}
            except Exception:  # noqa: BLE001
                return {"submitted": False, "reply": resp.message}
    except Exception as exc:  # noqa: BLE001
        log.warning("request_unspam failed: %s", exc)
        return {"submitted": False, "reply": None, "detail": str(exc)}


async def request_unfreeze(client) -> dict:
    """Best-effort unfreeze appeal via @SpamBot.

    Frozen accounts generally require an appeal form; this submits the @SpamBot
    entry point and reports its reply for the operator to continue manually.
    """
    try:
        resp = await _spambot_start(client)
        return {"submitted": True, "reply": resp.message}
    except Exception as exc:  # noqa: BLE001
        log.warning("request_unfreeze failed: %s", exc)
        return {"submitted": False, "reply": None, "detail": str(exc)}

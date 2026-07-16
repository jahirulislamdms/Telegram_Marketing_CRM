"""Telethon actions used by warmup (and later phases): join chats, send messages."""

import logging

from telethon.errors import (
    FloodWaitError,
    PeerFloodError,
    UserAlreadyParticipantError,
    UserBannedInChannelError,
)
from telethon.tl.functions.channels import InviteToChannelRequest, JoinChannelRequest
from telethon.tl.functions.messages import (
    AddChatUserRequest,
    ExportChatInviteRequest,
    ImportChatInviteRequest,
)
from telethon.tl.types import Channel

log = logging.getLogger("engine.actions")


def invite_hash(link: str) -> str | None:
    """Extract the invite hash from a private invite link, else None."""
    link = link.strip()
    if "joinchat/" in link:
        return link.rsplit("joinchat/", 1)[1].strip("/")
    if "t.me/+" in link:
        return link.rsplit("t.me/+", 1)[1].strip("/")
    if link.startswith("+"):
        return link[1:].strip("/")
    return None


def public_username(link: str) -> str:
    """Normalise a public link/username to a bare username."""
    username = link.strip()
    for prefix in ("https://t.me/", "http://t.me/", "t.me/", "@"):
        if username.startswith(prefix):
            username = username[len(prefix):]
            break
    return username.strip("/")


def coerce_target(target):
    """Normalise a send/add target for Telethon.

    Telethon needs an **int** for a numeric user/chat ID; a numeric *string* is
    otherwise misread as a username and fails with "Cannot find any entity".
    All-digit ids (optionally a leading '-' for chats/channels) become ints;
    ``@usernames`` and ``+phones`` stay strings. Non-string targets (ints,
    entity objects) pass through untouched.
    """
    if not isinstance(target, str):
        return target
    t = target.strip()
    if not t or t.startswith("@") or t.startswith("+"):
        return t
    if t.lstrip("-").isdigit():
        return int(t)
    return t


async def join_chat(client, link: str) -> dict:
    h = invite_hash(link)
    try:
        if h:
            await client(ImportChatInviteRequest(h))
            return {"joined": True, "via": "invite"}
        username = public_username(link)
        await client(JoinChannelRequest(username))
        return {"joined": True, "via": "public", "target": username}
    except UserAlreadyParticipantError:
        return {"joined": True, "already": True}


async def send_dm(client, target: str, text: str) -> dict:
    """Send a text message. Flood/peer-flood/ban warnings are returned (not raised)
    so the caller can auto-quarantine the account and pause sending."""
    target = coerce_target(target)
    try:
        await client.send_message(target, text)
        return {"sent": True}
    except FloodWaitError as exc:
        return {"sent": False, "error": "flood", "seconds": exc.seconds}
    except PeerFloodError:
        return {"sent": False, "error": "peerflood"}
    except UserBannedInChannelError:
        return {"sent": False, "error": "banned"}


async def send_file(client, target: str, file: str, caption: str | None = None) -> dict:
    # Telethon accepts a URL, local path, or bytes for ``file``.
    target = coerce_target(target)
    try:
        await client.send_file(target, file, caption=caption)
        return {"sent": True}
    except FloodWaitError as exc:
        return {"sent": False, "error": "flood", "seconds": exc.seconds}
    except PeerFloodError:
        return {"sent": False, "error": "peerflood"}


async def resolve_destination(client, link: str) -> dict:
    entity = await client.get_entity(link)
    if isinstance(entity, Channel):
        dtype = "channel" if getattr(entity, "broadcast", False) else "group"
    else:
        dtype = "group"
    return {
        "tg_entity_id": getattr(entity, "id", None),
        "title": getattr(entity, "title", None),
        "type": dtype,
    }


async def add_member(client, entity_id, target) -> dict:
    """Direct-add ``target`` to the destination; fall back to an invite link.

    Returns {state: added|invited|failed, method, error?, invite_link?}.
    """
    try:
        entity = await client.get_entity(coerce_target(entity_id))
        user = await client.get_entity(coerce_target(target))
    except Exception as exc:  # noqa: BLE001
        return {"state": "failed", "detail": f"resolve: {exc}"}

    # 1) Try a direct add.
    try:
        if isinstance(entity, Channel):
            await client(InviteToChannelRequest(entity, [user]))
        else:
            await client(AddChatUserRequest(entity.id, user, fwd_limit=10))
        return {"state": "added", "method": "direct_add"}
    except PeerFloodError:
        return {"state": "failed", "method": "direct_add", "error": "peerflood"}
    except FloodWaitError as exc:
        return {"state": "failed", "method": "direct_add", "error": "flood", "seconds": exc.seconds}
    except Exception as direct_exc:  # noqa: BLE001
        # 2) Fall back to sending a personal invite link.
        try:
            invite = await client(ExportChatInviteRequest(entity))
            link = getattr(invite, "link", None)
            await client.send_message(user, f"You're invited to join: {link}")
            return {"state": "invited", "method": "invite", "invite_link": link}
        except PeerFloodError:
            return {"state": "failed", "method": "invite", "error": "peerflood"}
        except FloodWaitError as exc:
            return {"state": "failed", "method": "invite", "error": "flood", "seconds": exc.seconds}
        except Exception as invite_exc:  # noqa: BLE001
            return {
                "state": "failed",
                "method": "invite",
                "detail": f"add={direct_exc}; invite={invite_exc}",
            }

"""Telethon actions used by warmup (and later phases): join chats, send messages."""

import logging

from telethon.errors import (
    FloodWaitError,
    PeerFloodError,
    UserAlreadyParticipantError,
    UserBannedInChannelError,
)
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.tl.functions.messages import ImportChatInviteRequest

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
    try:
        await client.send_file(target, file, caption=caption)
        return {"sent": True}
    except FloodWaitError as exc:
        return {"sent": False, "error": "flood", "seconds": exc.seconds}
    except PeerFloodError:
        return {"sent": False, "error": "peerflood"}

"""Telethon actions used by warmup (and later phases): join chats, send messages."""

import io
import logging

from telethon.errors import (
    FloodWaitError,
    PeerFloodError,
    UserAlreadyParticipantError,
    UserBannedInChannelError,
)
from telethon.tl.functions.channels import InviteToChannelRequest, JoinChannelRequest
from telethon.tl.functions.contacts import ImportContactsRequest
from telethon.tl.functions.messages import (
    AddChatUserRequest,
    ExportChatInviteRequest,
    ImportChatInviteRequest,
)
from telethon.tl.types import Channel, InputPhoneContact

log = logging.getLogger("engine.actions")


async def resolve_for_send(client, target):
    """Turn a phone-number target into a messageable user entity.

    Telegram cannot message a raw phone number — it must first be imported as a
    contact to resolve it to a user (same mechanism as phone lead resolution).
    Numeric ids, ``@usernames``, and already-resolved entities pass through
    unchanged. Raises ``ValueError`` when the phone has no Telegram account.
    """
    if isinstance(target, str) and target.startswith("+"):
        result = await client(
            ImportContactsRequest(
                [InputPhoneContact(client_id=0, phone=target, first_name="Lead", last_name="")]
            )
        )
        users = getattr(result, "users", None)
        if users:
            return users[0]
        raise ValueError(f"no Telegram account for {target}")
    return target


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
    so the caller can auto-quarantine the account and pause sending; any other
    failure (e.g. an unreachable phone) is also returned, never raised, so the
    engine never 500s on a bad recipient."""
    target = coerce_target(target)
    try:
        entity = await resolve_for_send(client, target)
        await client.send_message(entity, text)
        return {"sent": True}
    except FloodWaitError as exc:
        return {"sent": False, "error": "flood", "seconds": exc.seconds}
    except PeerFloodError:
        return {"sent": False, "error": "peerflood"}
    except UserBannedInChannelError:
        return {"sent": False, "error": "banned"}
    except Exception as exc:  # noqa: BLE001 - resolution/send failure -> clean error
        log.warning("send_dm failed for %r: %s", target, exc)
        return {"sent": False, "error": str(exc)[:200]}


async def send_file(client, target: str, file: str, caption: str | None = None) -> dict:
    # Telethon accepts a URL, local path, or bytes for ``file``.
    target = coerce_target(target)
    try:
        entity = await resolve_for_send(client, target)
        await client.send_file(entity, file, caption=caption)
        return {"sent": True}
    except FloodWaitError as exc:
        return {"sent": False, "error": "flood", "seconds": exc.seconds}
    except PeerFloodError:
        return {"sent": False, "error": "peerflood"}
    except Exception as exc:  # noqa: BLE001
        log.warning("send_file failed for %r: %s", target, exc)
        return {"sent": False, "error": str(exc)[:200]}


_DEFAULT_MEDIA_NAME = {
    "image": "photo.jpg",
    "video": "video.mp4",
    "voice": "voice.ogg",
    "audio": "audio.mp3",
    "file": "file.bin",
}


async def send_media(
    client, target, data: bytes, filename: str | None, mime: str | None,
    kind: str, caption: str | None,
) -> dict:
    """Upload media bytes to Telegram and send them to ``target``.

    The bytes come straight from the operator's browser and are never written to
    disk. Telethon infers the media type from the (in-memory) file's name; per-kind
    flags mark voice notes, streamable video, and forced documents.
    """
    target = coerce_target(target)
    bio = io.BytesIO(data)
    bio.name = filename or _DEFAULT_MEDIA_NAME.get(kind, "file.bin")
    kwargs: dict = {}
    if caption:
        kwargs["caption"] = caption
    if kind == "voice":
        kwargs["voice_note"] = True
    elif kind == "video":
        kwargs["supports_streaming"] = True
    elif kind == "file":
        kwargs["force_document"] = True
    try:
        entity = await resolve_for_send(client, target)
        msg = await client.send_file(entity, bio, **kwargs)
        return {"sent": True, "message_id": getattr(msg, "id", None)}
    except FloodWaitError as exc:
        return {"sent": False, "error": "flood", "seconds": exc.seconds}
    except PeerFloodError:
        return {"sent": False, "error": "peerflood"}
    except UserBannedInChannelError:
        return {"sent": False, "error": "banned"}
    except Exception as exc:  # noqa: BLE001
        log.warning("send_media failed for %r: %s", target, exc)
        return {"sent": False, "error": str(exc)[:200]}


async def download_media(client, peer, message_id) -> dict | None:
    """Fetch a message's media as bytes from Telegram.

    Nothing is written to disk — the bytes are returned to the caller, which
    streams them to the browser. Returns None when the message/media is gone
    (e.g. the peer deleted it), so the UI can show a placeholder.
    """
    peer = coerce_target(peer)
    try:
        msg = await client.get_messages(peer, ids=int(message_id))
    except Exception as exc:  # noqa: BLE001
        log.warning("download_media: get_messages failed: %s", exc)
        return None
    if msg is None or not getattr(msg, "media", None):
        return None
    data = await msg.download_media(file=bytes)
    if not data:
        return None
    f = getattr(msg, "file", None)
    return {
        "bytes": data,
        "mime": getattr(f, "mime_type", None) or "application/octet-stream",
        "name": getattr(f, "name", None),
    }


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

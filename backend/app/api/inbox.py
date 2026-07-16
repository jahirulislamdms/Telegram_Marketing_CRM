"""Unified live inbox: conversations, threads, replies, status, and the WS stream."""

import json

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Response,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_manager
from app.auth.security import ACCESS_TOKEN_TYPE, JWTError, decode_token
from app.db.models.contact import Contact
from app.db.models.inbox import Message
from app.db.models.proxy import Proxy
from app.db.models.user import User
from app.db.session import get_db
from app.realtime import manager, publish
from app.schemas.inbox import (
    BulkIds,
    BulkStatus,
    ConversationOut,
    MessageOut,
    SendReply,
    SetArchived,
    SetStatus,
    SimulateIncoming,
    ThreadOut,
)
from app.services import accounts as account_service
from app.services import audit
from app.services import engine_client
from app.services import inbox as inbox_service

router = APIRouter(prefix="/inbox", tags=["inbox"])


def _is_manager(user: User) -> bool:
    return user.role in ("admin", "manager")


async def _get_conversation_or_404(db: AsyncSession, conversation_id: int):
    conversation = await inbox_service.get_by_id(db, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    return conversation


async def _ensure_access(db: AsyncSession, user: User, conversation) -> None:
    if _is_manager(user):
        return
    if conversation.contact_id is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted")
    contact = await db.get(Contact, conversation.contact_id)
    if contact is None or contact.assigned_agent_id != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted")


async def _broadcast_message(db: AsyncSession, conversation, message) -> None:
    await publish(
        {
            "type": "message",
            "conversation": await inbox_service.conversation_dict(db, conversation),
            "message": inbox_service.message_dict(message),
        }
    )


async def _broadcast_conversation(db: AsyncSession, conversation) -> None:
    await publish(
        {
            "type": "conversation",
            "conversation": await inbox_service.conversation_dict(db, conversation),
        }
    )


# ------------------------------------------------------------- conversations -


@router.get("/conversations", response_model=list[ConversationOut])
async def list_conversations(
    account_id: int | None = Query(default=None),
    account_ids: str | None = Query(
        default=None, description="Comma-separated account ids; omit for all accounts"
    ),
    q: str | None = Query(default=None, description="Search peer/contact/last message"),
    conv_status: str | None = Query(default=None, alias="status"),
    unread: bool = Query(default=False),
    archived: bool = Query(default=False, description="true = the Archive folder"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    agent_filter = None if _is_manager(user) else user.id
    ids: list[int] | None = None
    if account_ids:
        try:
            ids = [int(x) for x in account_ids.split(",") if x.strip()]
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="account_ids must be integers"
            )
    conversations = await inbox_service.list_conversations(
        db,
        account_id=account_id,
        account_ids=ids,
        q=q,
        status=conv_status,
        unread_only=unread,
        archived=archived,
        assigned_agent_id=agent_filter,
    )
    return [await inbox_service.conversation_dict(db, c) for c in conversations]


@router.post("/conversations/{conversation_id}/archive", response_model=ConversationOut)
async def set_archived(
    conversation_id: int,
    payload: SetArchived,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    """Archive / unarchive a chat (15.1.i/j) — history is kept either way."""
    conversation = await _get_conversation_or_404(db, conversation_id)
    await _ensure_access(db, user, conversation)
    await inbox_service.set_archived(db, conversation, payload.archived)
    await _broadcast_conversation(db, conversation)
    return ConversationOut(**await inbox_service.conversation_dict(db, conversation))


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_conversation(
    conversation_id: int,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete our copy of a chat + its messages (15.1.i).

    Destructive and Admin/Manager-only; it never touches the peer's Telegram.
    """
    conversation = await _get_conversation_or_404(db, conversation_id)
    await audit.record_event(
        db, type="inbox.delete_conversation", actor_type="user", actor_id=user.id,
        entity_ref=f"conversation:{conversation_id}",
    )
    await inbox_service.delete_conversation(db, conversation)


@router.post("/conversations/{conversation_id}/save-contact")
async def save_contact(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Save an unlinked inbox peer as a CRM contact (15.1.d)."""
    conversation = await _get_conversation_or_404(db, conversation_id)
    await _ensure_access(db, user, conversation)
    if conversation.contact_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Conversation already has a contact"
        )
    if conversation.peer_id is None and not conversation.peer_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No peer identity to save"
        )
    contact = await inbox_service.save_peer_as_contact(db, conversation)
    await audit.record_event(
        db, type="inbox.save_contact", actor_type="user", actor_id=user.id,
        entity_ref=f"contact:{contact.id}",
    )
    await _broadcast_conversation(db, conversation)
    return {
        "id": contact.id,
        "label": contact.display_label,
        "username": contact.username,
        "phone": contact.phone,
        "telegram_user_id": contact.telegram_user_id,
        "stage": contact.stage,
        "source": contact.source,
        "consent": contact.consent,
    }


@router.get("/conversations/{conversation_id}", response_model=ThreadOut)
async def get_thread(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ThreadOut:
    conversation = await _get_conversation_or_404(db, conversation_id)
    await _ensure_access(db, user, conversation)
    messages = await inbox_service.get_thread(db, conversation_id)
    contact = None
    if conversation.contact_id:
        c = await db.get(Contact, conversation.contact_id)
        if c is not None:
            contact = {
                "id": c.id,
                "label": c.display_label,
                "phone": c.phone,
                "username": c.username,
                "stage": c.stage,
                "source": c.source,
                "tags": c.tags,
                "consent": c.consent,
                "opted_out": c.opted_out,
            }
    return ThreadOut(
        conversation=ConversationOut(**await inbox_service.conversation_dict(db, conversation)),
        messages=[MessageOut(**inbox_service.message_dict(m)) for m in messages],
        contact=contact,
    )


@router.get("/messages/{message_id}/media")
async def get_message_media(
    message_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """Stream a message's media, fetched on demand from Telegram (nothing stored).

    Returns 404 when the media is gone (e.g. the peer deleted it) so the UI can
    show a "media no longer available" placeholder.
    """
    message = await db.get(Message, message_id)
    if message is None or message.type in ("text", "link"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No media for this message")
    conversation = await _get_conversation_or_404(db, message.conversation_id)
    await _ensure_access(db, user, conversation)
    if message.tg_message_id is None or conversation.peer_id is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media reference unavailable")
    account = await account_service.get_by_id(db, message.account_id or conversation.account_id)
    if account is None or not account.session_ref:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Account not logged in")
    proxy = await db.get(Proxy, account.proxy_id) if account.proxy_id else None
    try:
        result = await engine_client.download_media(
            account, proxy, conversation.peer_id, message.tg_message_id
        )
    except engine_client.EngineUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    if result is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Media no longer available")
    filename = result.get("name") or f"media-{message_id}"
    disposition = "attachment" if message.type == "file" else "inline"
    return Response(
        content=result["bytes"],
        media_type=result.get("mime") or "application/octet-stream",
        headers={
            "Content-Disposition": f'{disposition}; filename="{filename}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


@router.post("/conversations/{conversation_id}/read", response_model=ConversationOut)
async def mark_read(
    conversation_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    conversation = await _get_conversation_or_404(db, conversation_id)
    await _ensure_access(db, user, conversation)
    await inbox_service.mark_read(db, conversation)
    await _broadcast_conversation(db, conversation)
    return ConversationOut(**await inbox_service.conversation_dict(db, conversation))


@router.patch("/conversations/{conversation_id}", response_model=ConversationOut)
async def set_status(
    conversation_id: int,
    payload: SetStatus,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    conversation = await _get_conversation_or_404(db, conversation_id)
    await _ensure_access(db, user, conversation)
    await inbox_service.set_status(db, conversation, payload.status)
    await _broadcast_conversation(db, conversation)
    return ConversationOut(**await inbox_service.conversation_dict(db, conversation))


@router.post("/conversations/{conversation_id}/send", response_model=MessageOut)
async def send_reply(
    conversation_id: int,
    payload: SendReply,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    conversation = await _get_conversation_or_404(db, conversation_id)
    await _ensure_access(db, user, conversation)

    account = await account_service.get_by_id(db, conversation.account_id)
    if account is None or not account.session_ref:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Conversation's account is not logged in",
        )
    target = await inbox_service.reply_target(db, conversation)
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No reachable recipient"
        )
    proxy = await db.get(Proxy, account.proxy_id) if account.proxy_id else None

    try:
        if payload.type == "image":
            if not payload.media_url:
                raise HTTPException(status_code=400, detail="media_url required for image")
            result = await engine_client.send_file(
                account, proxy, target, payload.media_url, payload.body
            )
        else:
            result = await engine_client.send_message(
                account, proxy, target, payload.body or ""
            )
    except engine_client.EngineUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    if not result.get("sent", False):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"send failed: {result.get('error')}",
        )

    message = await inbox_service.record_outgoing(
        db,
        conversation=conversation,
        account_id=account.id,
        agent_id=user.id,
        type=payload.type,
        body=payload.body,
        media_ref=payload.media_url,
    )
    await _broadcast_message(db, conversation, message)
    return MessageOut(**inbox_service.message_dict(message))


MAX_MEDIA_BYTES = 25 * 1024 * 1024
_MEDIA_KINDS = ("image", "video", "voice", "audio", "file")


@router.post("/conversations/{conversation_id}/send-media", response_model=MessageOut)
async def send_media(
    conversation_id: int,
    file: UploadFile = File(...),
    kind: str = Form("file"),
    caption: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> MessageOut:
    """Send image/video/file/voice from the composer, uploaded straight to Telegram.

    The uploaded bytes are forwarded to the engine and never written to the VPS
    disk. The outgoing message is recorded and re-rendered from Telegram like any
    other media message.
    """
    conversation = await _get_conversation_or_404(db, conversation_id)
    await _ensure_access(db, user, conversation)

    account = await account_service.get_by_id(db, conversation.account_id)
    if account is None or not account.session_ref:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Conversation's account is not logged in",
        )
    target = await inbox_service.reply_target(db, conversation)
    if target is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No reachable recipient")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if len(data) > MAX_MEDIA_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 25 MB)")
    if kind not in _MEDIA_KINDS:
        kind = "file"

    proxy = await db.get(Proxy, account.proxy_id) if account.proxy_id else None
    try:
        result = await engine_client.send_media(
            account, proxy, target, data, file.filename, file.content_type, kind, caption
        )
    except engine_client.EngineUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    if not result.get("sent", False):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"send failed: {result.get('error')}",
        )

    meta = {"kind": kind, "mime": file.content_type, "name": file.filename, "size": len(data)}
    message = await inbox_service.record_outgoing(
        db,
        conversation=conversation,
        account_id=account.id,
        agent_id=user.id,
        type=kind,
        body=caption,
        media_ref=json.dumps(meta),
        tg_message_id=result.get("message_id"),
    )
    await _broadcast_message(db, conversation, message)
    return MessageOut(**inbox_service.message_dict(message))


# ------------------------------------------------------------- bulk actions --


@router.post("/bulk/read", response_model=int)
async def bulk_read(
    payload: BulkIds,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> int:
    count = 0
    for cid in payload.conversation_ids:
        conversation = await inbox_service.get_by_id(db, cid)
        if conversation is not None:
            await inbox_service.mark_read(db, conversation)
            await _broadcast_conversation(db, conversation)
            count += 1
    return count


@router.post("/bulk/status", response_model=int)
async def bulk_status(
    payload: BulkStatus,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> int:
    count = 0
    for cid in payload.conversation_ids:
        conversation = await inbox_service.get_by_id(db, cid)
        if conversation is not None:
            await inbox_service.set_status(db, conversation, payload.status)
            await _broadcast_conversation(db, conversation)
            count += 1
    return count


# ---------------------------------------------- simulate incoming (dev/test) -


@router.post("/simulate-incoming", response_model=ConversationOut)
async def simulate_incoming(
    payload: SimulateIncoming,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> ConversationOut:
    """Inject an incoming message.

    In production, the engine's Telethon listener publishes real incoming
    messages via Redis; this endpoint drives the same record+broadcast path for
    development and testing.
    """
    conversation, message = await inbox_service.record_incoming(
        db,
        account_id=payload.account_id,
        peer_id=payload.peer_id,
        peer_name=payload.peer_name,
        peer_username=payload.peer_username,
        text=payload.text,
        msg_type=payload.msg_type,
        media_ref=payload.media_ref,
        tg_message_id=payload.tg_message_id,
    )
    await audit.record_event(
        db,
        type="inbox.simulate_incoming",
        actor_type="user",
        actor_id=user.id,
        entity_ref=f"conversation:{conversation.id}",
    )
    await _broadcast_message(db, conversation, message)
    return ConversationOut(**await inbox_service.conversation_dict(db, conversation))


# --------------------------------------------------------------- websocket ---


async def _authenticate_ws(token: str | None) -> int | None:
    if not token:
        return None
    try:
        payload = decode_token(token)
        if payload.get("type") != ACCESS_TOKEN_TYPE:
            return None
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError, TypeError):
        return None


async def inbox_ws(websocket: WebSocket) -> None:
    token = websocket.query_params.get("token")
    user_id = await _authenticate_ws(token)
    if user_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await manager.connect(websocket)
    try:
        await websocket.send_json({"type": "connected"})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:  # noqa: BLE001
        manager.disconnect(websocket)

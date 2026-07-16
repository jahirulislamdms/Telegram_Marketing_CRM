"""Inbox service: conversations, messages, and recording incoming/outgoing."""

from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.contact import Contact
from app.db.models.inbox import Conversation, Message

_OPT_OUT_WORDS = {"stop", "unsubscribe", "opt out", "optout", "unsub", "cancel"}


def is_opt_out(text: str | None) -> bool:
    t = (text or "").strip().lower()
    return t in _OPT_OUT_WORDS or t.startswith("stop")


def detect_type(body: str | None) -> str:
    if body and ("http://" in body or "https://" in body or "t.me/" in body):
        return "link"
    return "text"


def _preview(body: str | None) -> str | None:
    if not body:
        return None
    return body[:120]


async def get_by_id(db: AsyncSession, conversation_id: int) -> Conversation | None:
    return await db.get(Conversation, conversation_id)


async def _find_contact_by_peer(
    db: AsyncSession, peer_id: int | None, peer_username: str | None
) -> Contact | None:
    if peer_id is not None:
        res = await db.execute(
            select(Contact).where(Contact.telegram_user_id == peer_id)
        )
        contact = res.scalar_one_or_none()
        if contact is not None:
            return contact
    if peer_username:
        res = await db.execute(
            select(Contact).where(Contact.username == peer_username.lstrip("@").lower())
        )
        return res.scalar_one_or_none()
    return None


async def get_or_create_conversation(
    db: AsyncSession,
    *,
    account_id: int,
    peer_id: int | None,
    peer_name: str | None,
    contact_id: int | None = None,
) -> Conversation:
    if peer_id is not None:
        lookup = select(Conversation).where(
            Conversation.account_id == account_id, Conversation.peer_id == peer_id
        )
    elif contact_id is not None:
        lookup = select(Conversation).where(
            Conversation.account_id == account_id,
            Conversation.contact_id == contact_id,
        )
    else:
        lookup = select(Conversation).where(
            Conversation.account_id == account_id,
            Conversation.peer_id.is_(None),
            Conversation.contact_id.is_(None),
        )
    res = await db.execute(lookup)
    conversation = res.scalars().first()
    if conversation is None:
        conversation = Conversation(
            account_id=account_id,
            peer_id=peer_id,
            peer_name=peer_name,
            contact_id=contact_id,
            status="new",
        )
        db.add(conversation)
        await db.flush()
    elif contact_id and conversation.contact_id is None:
        conversation.contact_id = contact_id
    return conversation


async def record_incoming(
    db: AsyncSession,
    *,
    account_id: int,
    peer_id: int | None,
    peer_name: str | None,
    peer_username: str | None = None,
    text: str | None,
    msg_type: str | None = None,
    media_ref: str | None = None,
    tg_message_id: int | None = None,
) -> tuple[Conversation, Message]:
    contact = await _find_contact_by_peer(db, peer_id, peer_username)
    conversation = await get_or_create_conversation(
        db,
        account_id=account_id,
        peer_id=peer_id,
        peer_name=peer_name or (contact.display_label if contact else None),
        contact_id=contact.id if contact else None,
    )
    now = datetime.now(timezone.utc)
    kind = msg_type or detect_type(text)
    message = Message(
        conversation_id=conversation.id,
        direction="in",
        account_id=account_id,
        sender="contact",
        type=kind,
        body=text,
        media_ref=media_ref,
        tg_message_id=tg_message_id,
        status="delivered",
        created_at=now,
    )
    db.add(message)

    conversation.unread_count += 1
    conversation.last_message_at = now
    conversation.last_message_preview = _preview(text) or (
        f"[{kind}]" if kind not in ("text", "link") else None
    )

    # Consent guardrail: honor opt-out replies automatically and permanently.
    if is_opt_out(text):
        conversation.status = "opted_out"
        if contact is not None:
            contact.opted_out = True
            contact.stage = "opted_out"
    elif contact is not None and contact.stage in ("new", "contacted"):
        contact.stage = "replied"
        conversation.status = "replied"

    await db.commit()
    await db.refresh(conversation)
    await db.refresh(message)
    return conversation, message


async def record_outgoing(
    db: AsyncSession,
    *,
    conversation: Conversation,
    account_id: int,
    agent_id: int | None,
    type: str,
    body: str | None,
    media_ref: str | None = None,
    tg_message_id: int | None = None,
) -> Message:
    now = datetime.now(timezone.utc)
    message = Message(
        conversation_id=conversation.id,
        direction="out",
        account_id=account_id,
        sender=f"agent:{agent_id}" if agent_id else "system",
        type=type,
        body=body,
        media_ref=media_ref,
        tg_message_id=tg_message_id,
        status="sent",
        created_at=now,
    )
    db.add(message)
    conversation.last_message_at = now
    conversation.last_message_preview = _preview(body or ("[" + type + "]"))
    await db.commit()
    await db.refresh(message)
    return message


async def list_conversations(
    db: AsyncSession,
    *,
    account_id: int | None = None,
    status: str | None = None,
    unread_only: bool = False,
    assigned_agent_id: int | None = None,
) -> list[Conversation]:
    stmt = select(Conversation)
    if account_id is not None:
        stmt = stmt.where(Conversation.account_id == account_id)
    if status:
        stmt = stmt.where(Conversation.status == status)
    if unread_only:
        stmt = stmt.where(Conversation.unread_count > 0)
    if assigned_agent_id is not None:
        # Only conversations whose linked contact is assigned to this agent.
        sub = select(Contact.id).where(Contact.assigned_agent_id == assigned_agent_id)
        stmt = stmt.where(Conversation.contact_id.in_(sub))
    stmt = stmt.order_by(
        Conversation.last_message_at.desc().nullslast(), Conversation.id.desc()
    )
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def get_thread(db: AsyncSession, conversation_id: int) -> list[Message]:
    res = await db.execute(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.created_at, Message.id)
    )
    return list(res.scalars().all())


async def reply_target(db: AsyncSession, conversation: Conversation) -> str | None:
    """The identifier to send an outgoing reply to."""
    if conversation.peer_id:
        return str(conversation.peer_id)
    if conversation.contact_id:
        contact = await db.get(Contact, conversation.contact_id)
        if contact is not None:
            if contact.username:
                return f"@{contact.username}"
            if contact.phone:
                return contact.phone
    return None


async def mark_read(db: AsyncSession, conversation: Conversation) -> Conversation:
    conversation.unread_count = 0
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def set_status(
    db: AsyncSession, conversation: Conversation, status: str
) -> Conversation:
    conversation.status = status
    # Sync the linked contact's pipeline stage where the status maps to a stage.
    if conversation.contact_id and status != "blocked":
        contact = await db.get(Contact, conversation.contact_id)
        if contact is not None:
            contact.stage = status
            if status == "opted_out":
                contact.opted_out = True
    await db.commit()
    await db.refresh(conversation)
    return conversation


# ------------------------------------------------------------- serialising ---


async def contact_label(db: AsyncSession, conversation: Conversation) -> str:
    if conversation.contact_id:
        contact = await db.get(Contact, conversation.contact_id)
        if contact is not None:
            return contact.display_label
    return conversation.peer_name or (
        f"user {conversation.peer_id}" if conversation.peer_id else "unknown"
    )


def message_dict(message: Message) -> dict:
    return {
        "id": message.id,
        "conversation_id": message.conversation_id,
        "direction": message.direction,
        "account_id": message.account_id,
        "sender": message.sender,
        "type": message.type,
        "body": message.body,
        "media_ref": message.media_ref,
        "status": message.status,
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


async def conversation_dict(db: AsyncSession, conversation: Conversation) -> dict:
    return {
        "id": conversation.id,
        "contact_id": conversation.contact_id,
        "account_id": conversation.account_id,
        "peer_id": conversation.peer_id,
        "label": await contact_label(db, conversation),
        "last_message_at": conversation.last_message_at.isoformat()
        if conversation.last_message_at
        else None,
        "last_message_preview": conversation.last_message_preview,
        "unread_count": conversation.unread_count,
        "status": conversation.status,
    }

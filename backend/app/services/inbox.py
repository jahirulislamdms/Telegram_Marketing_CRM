"""Inbox service: conversations, messages, and recording incoming/outgoing."""

from datetime import datetime, timezone

from sqlalchemy import delete as sa_delete
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.account import Account
from app.db.models.constants import CONTACT_STAGES
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


def _norm_username(username: str | None) -> str | None:
    if not username:
        return None
    return username.lstrip("@").lower() or None


async def get_or_create_conversation(
    db: AsyncSession,
    *,
    account_id: int,
    peer_id: int | None,
    peer_name: str | None,
    peer_username: str | None = None,
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
            peer_username=_norm_username(peer_username),
            contact_id=contact_id,
            status="new",
        )
        db.add(conversation)
        await db.flush()
    else:
        if contact_id and conversation.contact_id is None:
            conversation.contact_id = contact_id
        # Backfill the peer's username/name once Telegram gives it to us.
        if peer_username and not conversation.peer_username:
            conversation.peer_username = _norm_username(peer_username)
        if peer_name and not conversation.peer_name:
            conversation.peer_name = peer_name
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
        peer_username=peer_username,
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


def _conversations_filter(
    stmt,
    *,
    account_id: int | None,
    account_ids: list[int] | None,
    q: str | None,
    status: str | None,
    unread_only: bool,
    archived: bool,
    assigned_agent_id: int | None,
):
    """Shared Conversation filters (list + count use the same predicates)."""
    # The main inbox shows non-archived chats; the Archive folder passes True — 15.1.j.
    stmt = stmt.where(Conversation.archived.is_(archived))
    if account_ids:
        # Multi-account selection (all / one / many) — 15.1.e.
        stmt = stmt.where(Conversation.account_id.in_(account_ids))
    elif account_id is not None:
        stmt = stmt.where(Conversation.account_id == account_id)
    if q:
        # Search conversations within the current selection — 15.1.g.
        like = f"%{q.strip().lower()}%"
        matching_contacts = select(Contact.id).where(
            or_(
                func.lower(Contact.name).like(like),
                func.lower(Contact.username).like(like),
                func.lower(Contact.phone).like(like),
            )
        )
        stmt = stmt.where(
            or_(
                func.lower(Conversation.peer_name).like(like),
                func.lower(Conversation.peer_username).like(like),
                func.lower(Conversation.last_message_preview).like(like),
                Conversation.contact_id.in_(matching_contacts),
            )
        )
    if status:
        stmt = stmt.where(Conversation.status == status)
    if unread_only:
        stmt = stmt.where(Conversation.unread_count > 0)
    if assigned_agent_id is not None:
        # Only conversations whose linked contact is assigned to this agent.
        sub = select(Contact.id).where(Contact.assigned_agent_id == assigned_agent_id)
        stmt = stmt.where(Conversation.contact_id.in_(sub))
    return stmt


async def count_conversations(
    db: AsyncSession,
    *,
    account_id: int | None = None,
    account_ids: list[int] | None = None,
    q: str | None = None,
    status: str | None = None,
    unread_only: bool = False,
    archived: bool = False,
    assigned_agent_id: int | None = None,
) -> int:
    stmt = _conversations_filter(
        select(func.count()).select_from(Conversation),
        account_id=account_id, account_ids=account_ids, q=q, status=status,
        unread_only=unread_only, archived=archived, assigned_agent_id=assigned_agent_id,
    )
    return int(await db.scalar(stmt) or 0)


async def list_conversations(
    db: AsyncSession,
    *,
    account_id: int | None = None,
    account_ids: list[int] | None = None,
    q: str | None = None,
    status: str | None = None,
    unread_only: bool = False,
    archived: bool = False,
    assigned_agent_id: int | None = None,
    limit: int | None = None,
    offset: int | None = None,
) -> list[Conversation]:
    stmt = _conversations_filter(
        select(Conversation),
        account_id=account_id, account_ids=account_ids, q=q, status=status,
        unread_only=unread_only, archived=archived, assigned_agent_id=assigned_agent_id,
    )
    stmt = stmt.order_by(
        Conversation.last_message_at.desc().nullslast(), Conversation.id.desc()
    )
    # Batched loading for large inboxes — 15.5 §4.
    if offset:
        stmt = stmt.offset(offset)
    if limit is not None:
        stmt = stmt.limit(limit)
    res = await db.execute(stmt)
    return list(res.scalars().all())


async def get_thread(
    db: AsyncSession,
    conversation_id: int,
    *,
    limit: int | None = None,
    before_id: int | None = None,
    q: str | None = None,
) -> list[Message]:
    """Messages for a conversation, always returned oldest→newest.

    ``limit`` returns the **newest** N (so a chat opens at the latest message —
    15.5 §3); ``before_id`` pages further back; ``q`` searches within this
    conversation only (15.5 §7).
    """
    stmt = select(Message).where(Message.conversation_id == conversation_id)
    if before_id is not None:
        stmt = stmt.where(Message.id < before_id)
    if q and q.strip():
        stmt = stmt.where(func.lower(Message.body).like(f"%{q.strip().lower()}%"))
    if limit is not None:
        # Take the newest N by id, then flip back to chronological order.
        res = await db.execute(stmt.order_by(Message.id.desc()).limit(limit))
        rows = list(res.scalars().all())
        rows.reverse()
        return rows
    res = await db.execute(stmt.order_by(Message.created_at, Message.id))
    return list(res.scalars().all())


async def has_older_messages(
    db: AsyncSession, conversation_id: int, oldest_id: int | None
) -> bool:
    """True when messages exist before ``oldest_id`` (drives "Load older")."""
    if oldest_id is None:
        return False
    stmt = (
        select(Message.id)
        .where(Message.conversation_id == conversation_id, Message.id < oldest_id)
        .limit(1)
    )
    return await db.scalar(stmt) is not None


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


async def set_archived(
    db: AsyncSession, conversation: Conversation, archived: bool
) -> Conversation:
    """Archive/unarchive a chat — 15.1.i. History is kept either way."""
    conversation.archived = archived
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def delete_conversation(db: AsyncSession, conversation: Conversation) -> None:
    """Operator-initiated removal of a chat + its messages from the CRM — 15.1.i.

    This only deletes *our* copy; it never touches the peer's Telegram. Messages
    are removed explicitly rather than relying on FK cascade, which SQLite does
    not enforce unless PRAGMA foreign_keys is on.
    """
    await db.execute(sa_delete(Message).where(Message.conversation_id == conversation.id))
    await db.delete(conversation)
    await db.commit()


async def save_peer_as_contact(
    db: AsyncSession,
    conversation: Conversation,
    *,
    name: str | None = None,
    phone: str | None = None,
    username: str | None = None,
    source: str | None = None,
    stage: str | None = None,
    consent: bool | None = None,
) -> Contact:
    """Create (or update) a CRM contact from an inbox peer — 15.1.d / 15.5 §6.

    The peer messaged us first, so a new contact defaults to ``consent=true`` and
    ``source="inbox"``, with its stage mirroring the conversation's status. Any
    supplied details override those defaults. If the peer (or the supplied
    phone/username) already matches a contact it is **updated in place** — a
    duplicate is never created. Raises ``contacts.DuplicateContact`` when a
    supplied phone/username belongs to a *different* contact.
    """
    from app.services import contacts as contact_service

    norm_phone = contact_service.normalize_phone(phone) if phone else None
    norm_username = (
        contact_service.normalize_username(username) if username else None
    )

    # Prefer an existing contact matching the typed identifiers, else the peer.
    contact: Contact | None = None
    if norm_phone or norm_username:
        res = await db.execute(
            select(Contact).where(
                or_(
                    Contact.phone == norm_phone if norm_phone else False,
                    Contact.username == norm_username if norm_username else False,
                )
            )
        )
        contact = res.scalars().first()
    if contact is None:
        contact = await _find_contact_by_peer(
            db, conversation.peer_id, conversation.peer_username
        )

    conflict = await contact_service.find_conflict(
        db,
        phone=norm_phone,
        username=norm_username,
        exclude_id=contact.id if contact is not None else None,
    )
    if conflict:
        raise contact_service.DuplicateContact(conflict)

    if contact is None:
        peer_username = _norm_username(conversation.peer_username)
        final_username = norm_username or peer_username
        default_stage = (
            conversation.status if conversation.status in CONTACT_STAGES else "replied"
        )
        contact = Contact(
            name=name or conversation.peer_name,
            lead_type="phone" if norm_phone else "username",
            phone=norm_phone,
            username=final_username,
            telegram_user_id=conversation.peer_id,
            resolution_status="resolved" if conversation.peer_id else "pending",
            source=source or "inbox",
            stage=stage or default_stage,
            consent=True if consent is None else consent,
            tags=[],
            utm={},
        )
        db.add(contact)
        await db.flush()
    else:
        # Update in place — never create a duplicate (15.5 §6).
        if name:
            contact.name = name
        if norm_phone:
            contact.phone = norm_phone
        if norm_username:
            contact.username = norm_username
        if source:
            contact.source = source
        if stage:
            contact.stage = stage
        if consent is not None:
            contact.consent = consent
        if contact.telegram_user_id is None and conversation.peer_id is not None:
            contact.telegram_user_id = conversation.peer_id
            contact.resolution_status = "resolved"
        contact.lead_type = "phone" if contact.phone else "username"

    conversation.contact_id = contact.id
    await db.commit()
    await db.refresh(contact)
    return contact


async def account_label(db: AsyncSession, account_id: int) -> str:
    account = await db.get(Account, account_id)
    return account.label if account is not None else f"#{account_id}"


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
        # Which account owns this conversation — 15.1.f.
        "account_label": await account_label(db, conversation.account_id),
        "peer_id": conversation.peer_id,
        "peer_username": conversation.peer_username,
        "label": await contact_label(db, conversation),
        "last_message_at": conversation.last_message_at.isoformat()
        if conversation.last_message_at
        else None,
        "last_message_preview": conversation.last_message_preview,
        "unread_count": conversation.unread_count,
        "status": conversation.status,
        "archived": conversation.archived,
    }

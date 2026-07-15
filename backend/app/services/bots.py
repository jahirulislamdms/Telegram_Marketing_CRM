"""Bots service: hosting control, subscribers, bot inbox, sending, broadcast."""

from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.bot import Bot, BotConversation, BotMessage, BotSubscriber
from app.realtime import publish
from app.services import engine_client


def _preview(body: str | None) -> str | None:
    return body[:120] if body else None


# --------------------------------------------------------------------- CRUD ---


async def list_bots(db: AsyncSession) -> list[Bot]:
    result = await db.execute(select(Bot).order_by(Bot.created_at.desc()))
    return list(result.scalars().all())


async def get_bot(db: AsyncSession, bot_id: int) -> Bot | None:
    return await db.get(Bot, bot_id)


async def create_bot(db: AsyncSession, token: str) -> Bot:
    bot = Bot(token=token, status="stopped")
    try:
        info = await engine_client.bot_info(token)
        bot.name = info.get("name")
        bot.username = info.get("username")
    except engine_client.EngineUnavailable:
        pass
    db.add(bot)
    await db.commit()
    await db.refresh(bot)
    return bot


async def start_bot(db: AsyncSession, bot: Bot) -> Bot:
    info = await engine_client.bot_start(bot.id, bot.token)
    bot.name = info.get("name") or bot.name
    bot.username = info.get("username") or bot.username
    bot.status = "running"
    await db.commit()
    await db.refresh(bot)
    return bot


async def stop_bot(db: AsyncSession, bot: Bot) -> Bot:
    try:
        await engine_client.bot_stop(bot.id, bot.token)
    except engine_client.EngineUnavailable:
        pass
    bot.status = "stopped"
    await db.commit()
    await db.refresh(bot)
    return bot


async def counts(db: AsyncSession, bot_id: int) -> dict:
    started = await db.scalar(
        select(func.count()).select_from(BotSubscriber).where(BotSubscriber.bot_id == bot_id)
    )
    active = await db.scalar(
        select(func.count()).select_from(BotSubscriber).where(
            BotSubscriber.bot_id == bot_id, BotSubscriber.is_active.is_(True)
        )
    )
    subscribed = await db.scalar(
        select(func.count()).select_from(BotSubscriber).where(
            BotSubscriber.bot_id == bot_id, BotSubscriber.is_subscribed.is_(True)
        )
    )
    return {"started": int(started or 0), "active": int(active or 0), "subscribed": int(subscribed or 0)}


# ------------------------------------------------------------ subscribers ----


async def upsert_subscriber(
    db: AsyncSession, bot_id: int, telegram_user_id: int, name: str | None, utm: str | None
) -> BotSubscriber:
    result = await db.execute(
        select(BotSubscriber).where(
            BotSubscriber.bot_id == bot_id,
            BotSubscriber.telegram_user_id == telegram_user_id,
        )
    )
    sub = result.scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if sub is None:
        sub = BotSubscriber(
            bot_id=bot_id, telegram_user_id=telegram_user_id, name=name,
            utm_source=utm, last_active_at=now,
        )
        db.add(sub)
        await db.flush()
    else:
        sub.last_active_at = now
        sub.is_active = True
        if name:
            sub.name = name
        if utm and not sub.utm_source:
            sub.utm_source = utm
    return sub


async def list_subscribers(db: AsyncSession, bot_id: int) -> list[BotSubscriber]:
    result = await db.execute(
        select(BotSubscriber).where(BotSubscriber.bot_id == bot_id).order_by(BotSubscriber.id.desc())
    )
    return list(result.scalars().all())


# ---------------------------------------------------------------- bot inbox ---


async def get_or_create_conversation(db: AsyncSession, bot_id: int, subscriber: BotSubscriber) -> BotConversation:
    result = await db.execute(
        select(BotConversation).where(
            BotConversation.bot_id == bot_id, BotConversation.subscriber_id == subscriber.id
        )
    )
    conv = result.scalar_one_or_none()
    if conv is None:
        conv = BotConversation(bot_id=bot_id, subscriber_id=subscriber.id, status="open")
        db.add(conv)
        await db.flush()
    return conv


async def record_incoming(
    db: AsyncSession, bot_id: int, telegram_user_id: int, name: str | None,
    text: str | None, utm: str | None = None, tg_message_id: int | None = None,
) -> tuple[BotConversation, BotMessage]:
    subscriber = await upsert_subscriber(db, bot_id, telegram_user_id, name, utm)
    conv = await get_or_create_conversation(db, bot_id, subscriber)
    now = datetime.now(timezone.utc)
    message = BotMessage(
        bot_conversation_id=conv.id, direction="in", sender="subscriber",
        type="text", body=text, tg_message_id=tg_message_id, created_at=now,
    )
    db.add(message)
    conv.unread_count += 1
    conv.last_message_at = now
    conv.last_message_preview = _preview(text)
    await db.commit()
    await db.refresh(conv)
    await db.refresh(message)
    return conv, message


async def list_conversations(db: AsyncSession, bot_id: int) -> list[BotConversation]:
    result = await db.execute(
        select(BotConversation).where(BotConversation.bot_id == bot_id)
        .order_by(BotConversation.last_message_at.desc().nullslast(), BotConversation.id.desc())
    )
    return list(result.scalars().all())


async def get_thread(db: AsyncSession, conversation_id: int) -> list[BotMessage]:
    result = await db.execute(
        select(BotMessage).where(BotMessage.bot_conversation_id == conversation_id)
        .order_by(BotMessage.created_at, BotMessage.id)
    )
    return list(result.scalars().all())


async def mark_read(db: AsyncSession, conv: BotConversation) -> BotConversation:
    conv.unread_count = 0
    await db.commit()
    await db.refresh(conv)
    return conv


async def reply(db: AsyncSession, bot: Bot, conv: BotConversation, agent_id: int | None, text: str) -> BotMessage:
    subscriber = await db.get(BotSubscriber, conv.subscriber_id)
    await engine_client.bot_send(bot.id, bot.token, subscriber.telegram_user_id, text)
    now = datetime.now(timezone.utc)
    message = BotMessage(
        bot_conversation_id=conv.id, direction="out",
        sender=f"agent:{agent_id}" if agent_id else "system", type="text",
        body=text, created_at=now,
    )
    db.add(message)
    conv.last_message_at = now
    conv.last_message_preview = _preview(text)
    await db.commit()
    await db.refresh(message)
    return message


async def broadcast(db: AsyncSession, bot: Bot, text: str) -> dict:
    subs = [s for s in await list_subscribers(db, bot.id) if s.is_subscribed and s.is_active]
    sent = 0
    for sub in subs:
        try:
            await engine_client.bot_send(bot.id, bot.token, sub.telegram_user_id, text)
            sent += 1
        except engine_client.EngineUnavailable:
            break
    return {"sent": sent, "recipients": len(subs)}


def deep_link(bot: Bot, utm: str | None) -> str:
    handle = bot.username or "your_bot"
    return f"https://t.me/{handle}?start={utm}" if utm else f"https://t.me/{handle}"


# ------------------------------------------------------------- serialising ---


async def conversation_dict(db: AsyncSession, conv: BotConversation) -> dict:
    subscriber = await db.get(BotSubscriber, conv.subscriber_id)
    label = (subscriber.name if subscriber and subscriber.name else
             f"user {subscriber.telegram_user_id}" if subscriber else "unknown")
    return {
        "id": conv.id, "bot_id": conv.bot_id, "subscriber_id": conv.subscriber_id,
        "label": label,
        "last_message_at": conv.last_message_at.isoformat() if conv.last_message_at else None,
        "last_message_preview": conv.last_message_preview,
        "unread_count": conv.unread_count, "status": conv.status,
    }


def message_dict(m: BotMessage) -> dict:
    return {
        "id": m.id, "bot_conversation_id": m.bot_conversation_id, "direction": m.direction,
        "sender": m.sender, "type": m.type, "body": m.body,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


async def broadcast_message_event(db: AsyncSession, conv: BotConversation, message: BotMessage) -> None:
    await publish({
        "type": "bot_message",
        "conversation": await conversation_dict(db, conv),
        "message": message_dict(message),
    })

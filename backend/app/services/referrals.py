"""Referral program: personal invite codes, referral counts, rewards.

A subscriber gets one personal ``Referral`` (find-or-create) carrying a unique
``invite_code``. The code is surfaced as a bot deep-link (``?start=ref_<code>``).
When a new subscriber starts the bot with that payload, :func:`record_referral`
increments the referrer's ``invited_count``.
"""

import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.bot import Bot, BotSubscriber
from app.db.models.referral import Referral

REFERRAL_PREFIX = "ref_"


async def _unique_code(db: AsyncSession) -> str:
    for _ in range(10):
        code = secrets.token_hex(4)
        exists = await db.scalar(select(Referral.id).where(Referral.invite_code == code))
        if exists is None:
            return code
    # Extremely unlikely; widen the space.
    return secrets.token_hex(8)


async def get_or_create_referral(db: AsyncSession, subscriber_id: int) -> Referral:
    result = await db.execute(
        select(Referral).where(Referral.referrer_subscriber_id == subscriber_id)
    )
    referral = result.scalar_one_or_none()
    if referral is None:
        referral = Referral(
            referrer_subscriber_id=subscriber_id,
            invite_code=await _unique_code(db),
        )
        db.add(referral)
        await db.commit()
        await db.refresh(referral)
    return referral


async def get_referral(db: AsyncSession, referral_id: int) -> Referral | None:
    return await db.get(Referral, referral_id)


async def by_code(db: AsyncSession, invite_code: str) -> Referral | None:
    code = invite_code[len(REFERRAL_PREFIX):] if invite_code.startswith(REFERRAL_PREFIX) else invite_code
    result = await db.execute(select(Referral).where(Referral.invite_code == code))
    return result.scalar_one_or_none()


async def record_referral(db: AsyncSession, invite_code: str) -> Referral | None:
    """Credit a referral by its (optionally ``ref_``-prefixed) code."""
    referral = await by_code(db, invite_code)
    if referral is None:
        return None
    referral.invited_count += 1
    await db.commit()
    await db.refresh(referral)
    return referral


async def maybe_record_from_payload(db: AsyncSession, payload: str | None) -> Referral | None:
    """If a bot-start payload is a referral link (``ref_<code>``), credit it."""
    if payload and payload.startswith(REFERRAL_PREFIX):
        return await record_referral(db, payload)
    return None


async def set_rewarded(db: AsyncSession, referral: Referral, rewarded: bool) -> Referral:
    referral.rewarded = rewarded
    await db.commit()
    await db.refresh(referral)
    return referral


def deep_link_payload(referral: Referral) -> str:
    return f"{REFERRAL_PREFIX}{referral.invite_code}"


async def leaderboard(db: AsyncSession, *, limit: int = 50) -> list[dict]:
    """Referrers ordered by invited_count (desc), with a display label."""
    result = await db.execute(
        select(Referral, BotSubscriber, Bot)
        .join(BotSubscriber, BotSubscriber.id == Referral.referrer_subscriber_id)
        .join(Bot, Bot.id == BotSubscriber.bot_id, isouter=True)
        .order_by(Referral.invited_count.desc(), Referral.id)
        .limit(limit)
    )
    rows: list[dict] = []
    for referral, subscriber, bot in result.all():
        label = (
            subscriber.name
            if subscriber and subscriber.name
            else (f"user {subscriber.telegram_user_id}" if subscriber else "unknown")
        )
        rows.append(
            {
                "referral_id": referral.id,
                "subscriber_id": referral.referrer_subscriber_id,
                "label": label,
                "bot_name": bot.name if bot else None,
                "invite_code": referral.invite_code,
                "invited_count": referral.invited_count,
                "rewarded": referral.rewarded,
            }
        )
    return rows

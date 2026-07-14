"""Audit / event log service."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.constants import ActorType
from app.db.models.event import Event


async def record_event(
    db: AsyncSession,
    *,
    type: str,
    actor_type: str = ActorType.system.value,
    actor_id: int | None = None,
    entity_ref: str | None = None,
    meta: dict | None = None,
) -> Event:
    event = Event(
        type=type,
        actor_type=actor_type,
        actor_id=actor_id,
        entity_ref=entity_ref,
        meta=meta or {},
    )
    db.add(event)
    await db.commit()
    await db.refresh(event)
    return event


async def list_events(db: AsyncSession, *, limit: int = 100) -> list[Event]:
    result = await db.execute(
        select(Event).order_by(Event.created_at.desc(), Event.id.desc()).limit(limit)
    )
    return list(result.scalars().all())

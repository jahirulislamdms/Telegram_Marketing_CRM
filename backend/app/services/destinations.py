"""Destinations & "Add members": register, queue, paced add with invite fallback."""

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.account import Account
from app.db.models.contact import Contact
from app.db.models.destination import Destination, GroupMembership
from app.db.models.proxy import Proxy
from app.services import engine_client
from app.services.contacts import normalize_phone, normalize_username
from app.services.sender import eligible_accounts
from worker.antiban import pacing

# in-destination states (i.e. "already there / invited / joined")
IN_DESTINATION_STATES = ("added", "invited", "joined")

# execute(account, membership, contact) -> engine add_member result dict
ExecuteFn = Callable[[Account, GroupMembership, Contact], Awaitable[dict]]


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------- CRUD ---


async def list_destinations(db: AsyncSession) -> list[Destination]:
    result = await db.execute(select(Destination).order_by(Destination.created_at.desc()))
    return list(result.scalars().all())


async def get_destination(db: AsyncSession, destination_id: int) -> Destination | None:
    return await db.get(Destination, destination_id)


async def _resolver_account(db: AsyncSession) -> Account | None:
    accounts = await eligible_accounts(db)
    return accounts[0] if accounts else None


async def register_destination(db: AsyncSession, link: str) -> Destination:
    """Register a group/channel; resolve it via the engine when possible."""
    destination = Destination(link=link)
    account = await _resolver_account(db)
    if account is not None:
        proxy = await db.get(Proxy, account.proxy_id) if account.proxy_id else None
        try:
            data = await engine_client.resolve_destination(account, proxy, link)
            destination.title = data.get("title")
            destination.tg_entity_id = data.get("tg_entity_id")
            destination.type = data.get("type", "unknown")
            destination.added_via = account.id
        except engine_client.EngineUnavailable:
            pass  # store unresolved; can be resolved on a later attempt
    db.add(destination)
    await db.commit()
    await db.refresh(destination)
    return destination


async def get_memberships(db: AsyncSession, destination_id: int) -> list[GroupMembership]:
    result = await db.execute(
        select(GroupMembership)
        .where(GroupMembership.destination_id == destination_id)
        .order_by(GroupMembership.id)
    )
    return list(result.scalars().all())


async def already_member_contact_ids(db: AsyncSession, destination_id: int) -> set[int]:
    result = await db.execute(
        select(GroupMembership.contact_id).where(
            GroupMembership.destination_id == destination_id,
            GroupMembership.state.in_(IN_DESTINATION_STATES),
        )
    )
    return {row[0] for row in result.all()}


async def contact_destination_ids(db: AsyncSession, contact_id: int) -> list[int]:
    result = await db.execute(
        select(GroupMembership.destination_id).where(
            GroupMembership.contact_id == contact_id,
            GroupMembership.state.in_(IN_DESTINATION_STATES),
        )
    )
    return [row[0] for row in result.all()]


# ---------------------------------------------------------- build the list ---


async def _find_or_create_contact(db: AsyncSession, identifier: str) -> Contact | None:
    ident = identifier.strip()
    if not ident:
        return None
    is_phone = ident.startswith("+") or ident.replace("+", "").isdigit()
    if is_phone:
        phone = normalize_phone(ident)
        if not phone:
            return None
        existing = await db.execute(select(Contact).where(Contact.phone == phone))
        found = existing.scalar_one_or_none()
        if found:
            return found
        contact = Contact(
            lead_type="phone", phone=phone, consent=True, source="add_members",
            tags=[], utm={},
        )
    else:
        username = normalize_username(ident)
        if not username:
            return None
        existing = await db.execute(select(Contact).where(Contact.username == username))
        found = existing.scalar_one_or_none()
        if found:
            return found
        contact = Contact(
            lead_type="username", username=username, consent=True, source="add_members",
            tags=[], utm={},
        )
    db.add(contact)
    await db.flush()
    return contact


async def add_members(
    db: AsyncSession,
    destination: Destination,
    *,
    contact_ids: list[int] | None = None,
    identifiers: list[str] | None = None,
) -> dict:
    """Queue consented contacts (and typed identifiers) as pending memberships.

    Contacts already in the destination (or already queued) are excluded.
    """
    contacts: list[Contact] = []
    if contact_ids:
        res = await db.execute(
            select(Contact).where(
                Contact.id.in_(contact_ids),
                Contact.consent.is_(True),
                Contact.opted_out.is_(False),
            )
        )
        contacts.extend(res.scalars().all())
    for identifier in identifiers or []:
        contact = await _find_or_create_contact(db, identifier)
        if contact is not None:
            contacts.append(contact)

    existing = {m.contact_id for m in await get_memberships(db, destination.id)}
    queued = skipped = 0
    seen: set[int] = set()
    for contact in contacts:
        if contact.id in existing or contact.id in seen:
            skipped += 1
            continue
        seen.add(contact.id)
        db.add(
            GroupMembership(
                contact_id=contact.id, destination_id=destination.id, state="pending"
            )
        )
        queued += 1
    await db.commit()
    return {"queued": queued, "skipped_existing": skipped}


# --------------------------------------------------------------------- tick ---


def build_add_executor(db: AsyncSession) -> ExecuteFn:
    async def _execute(account: Account, membership: GroupMembership, contact: Contact) -> dict:
        target = (
            str(contact.telegram_user_id)
            if contact.telegram_user_id
            else (f"@{contact.username}" if contact.username else contact.phone)
        )
        if not target:
            return {"state": "failed", "detail": "no reachable identifier"}
        destination = await db.get(Destination, membership.destination_id)
        if destination is None or destination.tg_entity_id is None:
            return {"state": "failed", "detail": "destination not resolved"}
        proxy = await db.get(Proxy, account.proxy_id) if account.proxy_id else None
        try:
            return await engine_client.add_member(
                account, proxy, destination.tg_entity_id, target
            )
        except engine_client.EngineUnavailable:
            return {"state": "failed", "error": "engine_unavailable"}

    return _execute


async def _pending(db: AsyncSession, destination_id: int) -> list[GroupMembership]:
    result = await db.execute(
        select(GroupMembership)
        .where(
            GroupMembership.destination_id == destination_id,
            GroupMembership.state == "pending",
        )
        .order_by(GroupMembership.id)
    )
    return list(result.scalars().all())


async def run_add_tick(
    db: AsyncSession,
    destination: Destination,
    now: datetime,
    execute: ExecuteFn,
    *,
    min_delay: int | None = None,
) -> dict:
    now = _as_utc(now)
    min_delay = min_delay if min_delay is not None else settings.send_min_delay_seconds
    summary = {"added": 0, "invited": 0, "failed": 0, "paused": False, "actions": []}

    if destination.tg_entity_id is None:
        summary["detail"] = "destination not resolved"
        return summary

    accounts = await eligible_accounts(db)
    usable = [
        a
        for a in accounts
        if pacing.under_daily_cap(a.actions_today, a.daily_cap)
        and pacing.delay_ok(_as_utc(a.last_action_at), now, min_delay)
    ]
    if not usable:
        return summary
    accounts_by_id = {a.id: a for a in usable}
    order_ids = pacing.rotate(list(accounts_by_id), None)

    pending = await _pending(db, destination.id)
    ti = 0
    for account_id in order_ids:
        if ti >= len(pending):
            break
        account = accounts_by_id[account_id]
        membership = pending[ti]
        contact = await db.get(Contact, membership.contact_id)
        if contact is None:
            membership.state = "failed"
            membership.error = "contact removed"
            summary["failed"] += 1
            ti += 1
            continue

        result = await execute(account, membership, contact)
        error = result.get("error")
        if error in ("flood", "peerflood"):
            # Anti-ban: quarantine and stop; leave this membership pending to retry.
            account.status = "quarantined"
            summary["paused"] = True
            summary["warning"] = error
            break

        state = result.get("state", "failed")
        membership.state = state
        membership.method = result.get("method")
        membership.account_id = account.id
        membership.error = result.get("detail") if state == "failed" else None
        account.actions_today += 1
        account.last_action_at = now
        summary[state if state in ("added", "invited") else "failed"] += 1
        summary["actions"].append(
            {"account_id": account.id, "contact_id": contact.id, "state": state}
        )
        ti += 1

    await db.commit()
    return summary

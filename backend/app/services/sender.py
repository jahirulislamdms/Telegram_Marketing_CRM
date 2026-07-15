"""Sender engine: paced, rotated, anti-ban outreach to consented contacts."""

import random
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.account import Account
from app.db.models.contact import Contact
from app.db.models.proxy import Proxy
from app.db.models.sender import SendJob, SendTarget
from app.realtime import publish
from app.services import engine_client
from app.services import inbox as inbox_service
from worker.antiban import pacing
from worker.antiban.spintax import spin

# execute(account, contact, body) -> {"ok": bool, "warning"?: str}
ExecuteFn = Callable[[Account, Contact, str], Awaitable[dict]]


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def render_message(job: SendJob, contact: Contact, rng: random.Random | None = None) -> str:
    body = spin(job.template, rng)
    if job.include_link and job.link_url:
        first_contact = contact.last_contacted_at is None
        if not (job.suppress_link_first and first_contact):
            body = f"{body}\n{job.link_url}"
    return body


# --------------------------------------------------------------------- CRUD ---


async def list_jobs(db: AsyncSession) -> list[SendJob]:
    result = await db.execute(select(SendJob).order_by(SendJob.created_at.desc()))
    return list(result.scalars().all())


async def get_job(db: AsyncSession, job_id: int) -> SendJob | None:
    return await db.get(SendJob, job_id)


async def create_job(
    db: AsyncSession,
    *,
    name: str,
    template: str,
    include_link: bool,
    link_url: str | None,
    suppress_link_first: bool,
    created_by: int | None,
) -> SendJob:
    job = SendJob(
        name=name,
        template=template,
        include_link=include_link,
        link_url=link_url,
        suppress_link_first=suppress_link_first,
        created_by=created_by,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


async def get_targets(db: AsyncSession, job_id: int) -> list[SendTarget]:
    result = await db.execute(
        select(SendTarget).where(SendTarget.job_id == job_id).order_by(SendTarget.id)
    )
    return list(result.scalars().all())


async def target_stats(db: AsyncSession, job_id: int) -> dict:
    result = await db.execute(
        select(SendTarget.status, func.count())
        .where(SendTarget.job_id == job_id)
        .group_by(SendTarget.status)
    )
    stats = {"queued": 0, "sent": 0, "replied": 0, "failed": 0, "skipped": 0}
    for status, count in result.all():
        stats[status] = count
    return stats


async def add_targets(
    db: AsyncSession,
    job: SendJob,
    *,
    contact_ids: list[int] | None = None,
    source: str | None = None,
) -> int:
    """Add consented, non-opted-out contacts as queued targets (deduped)."""
    stmt = select(Contact).where(Contact.consent.is_(True), Contact.opted_out.is_(False))
    if contact_ids:
        stmt = stmt.where(Contact.id.in_(contact_ids))
    if source:
        stmt = stmt.where(Contact.source == source)
    contacts = list((await db.execute(stmt)).scalars().all())

    existing = {t.contact_id for t in await get_targets(db, job.id)}
    added = 0
    for contact in contacts:
        if contact.id in existing:
            continue
        db.add(SendTarget(job_id=job.id, contact_id=contact.id, status="queued"))
        added += 1
    await db.commit()
    return added


async def start_job(db: AsyncSession, job: SendJob) -> SendJob:
    job.status = "running"
    if job.started_at is None:
        job.started_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(job)
    return job


async def pause_job(db: AsyncSession, job: SendJob) -> SendJob:
    job.status = "paused"
    await db.commit()
    await db.refresh(job)
    return job


async def stop_job(db: AsyncSession, job: SendJob) -> SendJob:
    job.status = "done"
    await db.commit()
    await db.refresh(job)
    return job


# --------------------------------------------------------------------- tick ---


async def eligible_accounts(db: AsyncSession) -> list[Account]:
    """Active, logged-in accounts (not warming/quarantined/banned)."""
    result = await db.execute(
        select(Account)
        .where(Account.status == "active", Account.session_ref.isnot(None))
        .order_by(Account.id)
    )
    return list(result.scalars().all())


async def _queued_targets(db: AsyncSession, job_id: int) -> list[SendTarget]:
    result = await db.execute(
        select(SendTarget)
        .where(SendTarget.job_id == job_id, SendTarget.status == "queued")
        .order_by(SendTarget.id)
    )
    return list(result.scalars().all())


def build_executor(db: AsyncSession, agent_id: int | None) -> ExecuteFn:
    """Real executor: send via the engine and land the message in the inbox."""

    async def _execute(account: Account, contact: Contact, body: str) -> dict:
        target = (
            str(contact.telegram_user_id)
            if contact.telegram_user_id
            else (f"@{contact.username}" if contact.username else contact.phone)
        )
        if not target:
            return {"ok": False, "error": "no_target"}
        proxy = await db.get(Proxy, account.proxy_id) if account.proxy_id else None
        try:
            result = await engine_client.send_message(account, proxy, target, body)
        except engine_client.EngineUnavailable:
            return {"ok": False, "warning": "engine_unavailable"}
        if not result.get("sent"):
            return {"ok": False, "warning": result.get("error", "warning")}

        conversation = await inbox_service.get_or_create_conversation(
            db,
            account_id=account.id,
            peer_id=contact.telegram_user_id,
            peer_name=contact.display_label,
            contact_id=contact.id,
        )
        message = await inbox_service.record_outgoing(
            db,
            conversation=conversation,
            account_id=account.id,
            agent_id=agent_id,
            type="text",
            body=body,
        )
        await publish(
            {
                "type": "message",
                "conversation": await inbox_service.conversation_dict(db, conversation),
                "message": inbox_service.message_dict(message),
            }
        )
        return {"ok": True}

    return _execute


async def run_tick(
    db: AsyncSession,
    job: SendJob,
    now: datetime,
    execute: ExecuteFn,
    *,
    rng: random.Random | None = None,
    min_delay: int | None = None,
) -> dict:
    now = _as_utc(now)
    rng = rng or random.Random()
    min_delay = min_delay if min_delay is not None else settings.send_min_delay_seconds
    summary = {"sent": 0, "skipped": 0, "failed": 0, "paused": False, "actions": []}

    if job.status != "running":
        return summary

    accounts = await eligible_accounts(db)
    usable = [
        a
        for a in accounts
        if pacing.under_daily_cap(a.actions_today, a.daily_cap)
        and pacing.in_window(now, job.active_start, job.active_end)
        and pacing.delay_ok(_as_utc(a.last_action_at), now, min_delay)
    ]
    if not usable:
        return summary
    accounts_by_id = {a.id: a for a in usable}
    order_ids = pacing.rotate(list(accounts_by_id), job.last_account_id)

    # Pre-filter queued targets, marking non-consented/opted-out as skipped.
    valid: list[tuple[SendTarget, Contact]] = []
    for target in await _queued_targets(db, job.id):
        contact = await db.get(Contact, target.contact_id)
        if contact is None or not contact.consent or contact.opted_out:
            target.status = "skipped"
            summary["skipped"] += 1
        else:
            valid.append((target, contact))

    ti = 0
    for account_id in order_ids:
        if ti >= len(valid):
            break
        account = accounts_by_id[account_id]
        target, contact = valid[ti]
        body = render_message(job, contact, rng)
        result = await execute(account, contact, body)

        if result.get("ok"):
            target.status = "sent"
            target.account_id = account.id
            target.sent_at = now
            target.rendered_body = body
            account.actions_today += 1
            account.last_action_at = now
            job.last_account_id = account.id
            if contact.stage == "new":
                contact.stage = "contacted"
            contact.last_contacted_at = now
            summary["sent"] += 1
            summary["actions"].append({"account_id": account.id, "contact_id": contact.id})
            ti += 1
        elif result.get("warning"):
            # Flood / peer-flood / ban / engine warning: quarantine + auto-pause.
            warning = result["warning"]
            account.status = "quarantined"
            job.status = "paused"
            target.status = "failed"
            target.error = str(warning)[:255]
            summary["failed"] += 1
            summary["paused"] = True
            summary["warning"] = warning
            break
        else:
            # Per-target failure (e.g. no reachable identifier): skip, keep going.
            target.status = "failed"
            target.error = str(result.get("error", "failed"))[:255]
            summary["failed"] += 1
            ti += 1

    # Complete the job when nothing is left to send.
    if job.status == "running":
        remaining = await db.scalar(
            select(func.count())
            .select_from(SendTarget)
            .where(SendTarget.job_id == job.id, SendTarget.status == "queued")
        )
        if not remaining:
            job.status = "done"

    await db.commit()
    return summary

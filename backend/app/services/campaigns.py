"""Campaigns: templates, segments, drip, A/B split, paced execution, reporting."""

import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.account import Account
from app.db.models.campaign import Campaign, CampaignTarget, Template
from app.db.models.contact import Contact
from app.db.models.destination import Destination, GroupMembership
from app.db.models.proxy import Proxy
from app.realtime import publish
from app.services import contacts as contact_service
from app.services import engine_client
from app.services import inbox as inbox_service
from app.services.destinations import already_member_contact_ids
from app.services.sender import eligible_accounts
from worker.antiban import pacing
from worker.antiban.spintax import spin


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def render_template(template: Template, contact: Contact, rng: random.Random | None = None) -> str:
    body = spin(template.body, rng)
    if template.include_link and template.link_url:
        first_contact = contact.last_contacted_at is None
        if not first_contact:  # suppress link on the very first message
            body = f"{body}\n{template.link_url}"
    return body


# ---------------------------------------------------------------- templates ---


async def list_templates(db: AsyncSession) -> list[Template]:
    result = await db.execute(select(Template).order_by(Template.variant_group, Template.id))
    return list(result.scalars().all())


async def get_template(db: AsyncSession, template_id: int) -> Template | None:
    return await db.get(Template, template_id)


async def variants_in_group(db: AsyncSession, variant_group: str) -> list[Template]:
    result = await db.execute(
        select(Template).where(Template.variant_group == variant_group).order_by(Template.id)
    )
    return list(result.scalars().all())


async def create_template(
    db: AsyncSession,
    *,
    name: str,
    body: str,
    include_link: bool,
    link_url: str | None,
    variant_group: str,
    variant_label: str,
    created_by: int | None,
) -> Template:
    template = Template(
        name=name,
        body=body,
        include_link=include_link,
        link_url=link_url,
        variant_group=variant_group,
        variant_label=variant_label,
        created_by=created_by,
    )
    db.add(template)
    await db.commit()
    await db.refresh(template)
    return template


# ---------------------------------------------------------------- campaigns ---


async def list_campaigns(db: AsyncSession) -> list[Campaign]:
    result = await db.execute(select(Campaign).order_by(Campaign.created_at.desc()))
    return list(result.scalars().all())


async def get_campaign(db: AsyncSession, campaign_id: int) -> Campaign | None:
    return await db.get(Campaign, campaign_id)


async def create_campaign(
    db: AsyncSession,
    *,
    name: str,
    action: str,
    destination_id: int | None,
    segment: dict,
    steps: list,
    ab_test: bool,
    created_by: int | None,
) -> Campaign:
    campaign = Campaign(
        name=name,
        action=action,
        destination_id=destination_id,
        segment=segment,
        steps=steps,
        ab_test=ab_test,
        created_by=created_by,
    )
    db.add(campaign)
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def build_segment(db: AsyncSession, segment: dict) -> list[Contact]:
    """Consented, non-opted-out contacts matching the segment filter."""
    stmt = select(Contact).where(Contact.consent.is_(True), Contact.opted_out.is_(False))
    if segment.get("source"):
        stmt = stmt.where(Contact.source == segment["source"])
    if segment.get("stage"):
        stmt = stmt.where(Contact.stage == segment["stage"])
    contacts = list((await db.execute(stmt)).scalars().all())

    tag = segment.get("tag")
    if tag:
        contacts = [c for c in contacts if tag in (c.tags or [])]

    exclude_dest = segment.get("exclude_in_destination")
    if exclude_dest:
        already = await already_member_contact_ids(db, int(exclude_dest))
        contacts = [c for c in contacts if c.id not in already]
    return contacts


async def get_targets(db: AsyncSession, campaign_id: int) -> list[CampaignTarget]:
    result = await db.execute(
        select(CampaignTarget)
        .where(CampaignTarget.campaign_id == campaign_id)
        .order_by(CampaignTarget.scheduled_at, CampaignTarget.id)
    )
    return list(result.scalars().all())


async def materialize_targets(db: AsyncSession, campaign: Campaign, now: datetime) -> int:
    contacts = await build_segment(db, campaign.segment or {})
    steps = campaign.steps or [{"offset_hours": 0}]
    created = 0
    for step_index, step in enumerate(steps):
        variant_group = step.get("variant_group")
        variants = await variants_in_group(db, variant_group) if variant_group else []
        offset = int(step.get("offset_hours", 0))
        scheduled = now + timedelta(hours=offset)
        for contact in contacts:
            template_id = None
            if variants:
                idx = (contact.id % len(variants)) if campaign.ab_test else 0
                template_id = variants[idx].id
            db.add(
                CampaignTarget(
                    campaign_id=campaign.id,
                    contact_id=contact.id,
                    step=step_index,
                    template_id=template_id,
                    scheduled_at=scheduled,
                    result="queued",
                )
            )
            created += 1
    await db.commit()
    return created


async def start_campaign(db: AsyncSession, campaign: Campaign, now: datetime) -> Campaign:
    first_start = campaign.started_at is None
    campaign.status = "running"
    if first_start:
        campaign.started_at = now
    await db.commit()
    if first_start:
        await materialize_targets(db, campaign, now)
    await db.refresh(campaign)
    return campaign


async def pause_campaign(db: AsyncSession, campaign: Campaign) -> Campaign:
    campaign.status = "paused"
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def stop_campaign(db: AsyncSession, campaign: Campaign) -> Campaign:
    campaign.status = "done"
    await db.commit()
    await db.refresh(campaign)
    return campaign


# --------------------------------------------------------------------- tick ---


async def _record_membership(
    db: AsyncSession, contact: Contact, destination: Destination, state: str,
    method: str | None, account_id: int,
) -> None:
    existing = await db.execute(
        select(GroupMembership).where(
            GroupMembership.contact_id == contact.id,
            GroupMembership.destination_id == destination.id,
        )
    )
    membership = existing.scalar_one_or_none()
    if membership is None:
        membership = GroupMembership(
            contact_id=contact.id, destination_id=destination.id, state=state,
            method=method, account_id=account_id,
        )
        db.add(membership)
    else:
        membership.state = state
        membership.method = method
        membership.account_id = account_id


async def _execute_target(
    db: AsyncSession,
    campaign: Campaign,
    destination: Destination | None,
    account: Account,
    target: CampaignTarget,
    contact: Contact,
    now: datetime,
    agent_id: int | None,
    rng: random.Random,
) -> dict:
    # Re-resolvable target so any rotated account can reach the contact.
    ident = contact_service.send_identifier(contact)
    if not ident:
        return {"result": "failed", "detail": "no reachable identifier"}
    proxy = await db.get(Proxy, account.proxy_id) if account.proxy_id else None

    if campaign.action == "message":
        template = await db.get(Template, target.template_id) if target.template_id else None
        body = render_template(template, contact, rng) if template else ""
        try:
            result = await engine_client.send_message(account, proxy, ident, body)
        except engine_client.EngineUnavailable:
            return {"warning": "engine_unavailable"}
        if not result.get("sent"):
            error = result.get("error")
            if error in ("flood", "peerflood"):
                return {"warning": error}
            return {"result": "failed", "detail": error}
        conversation = await inbox_service.get_or_create_conversation(
            db, account_id=account.id, peer_id=contact.telegram_user_id,
            peer_name=contact.display_label, contact_id=contact.id,
        )
        message = await inbox_service.record_outgoing(
            db, conversation=conversation, account_id=account.id, agent_id=agent_id,
            type="text", body=body,
        )
        await publish(
            {
                "type": "message",
                "conversation": await inbox_service.conversation_dict(db, conversation),
                "message": inbox_service.message_dict(message),
            }
        )
        return {"result": "sent"}

    # action in ("add", "invite")
    if destination is None or destination.tg_entity_id is None:
        return {"result": "failed", "detail": "destination not resolved"}
    try:
        result = await engine_client.add_member(account, proxy, destination.tg_entity_id, ident)
    except engine_client.EngineUnavailable:
        return {"warning": "engine_unavailable"}
    error = result.get("error")
    if error in ("flood", "peerflood"):
        return {"warning": error}
    state = result.get("state")
    if state in ("added", "invited"):
        await _record_membership(db, contact, destination, state, result.get("method"), account.id)
        return {"result": "joined"}
    return {"result": "failed", "detail": result.get("detail") or "add failed"}


async def run_tick(
    db: AsyncSession,
    campaign: Campaign,
    now: datetime,
    *,
    min_delay: int | None = None,
    agent_id: int | None = None,
) -> dict:
    now = _as_utc(now)
    rng = random.Random()
    min_delay = min_delay if min_delay is not None else settings.send_min_delay_seconds
    summary = {"sent": 0, "joined": 0, "failed": 0, "skipped": 0, "paused": False, "actions": []}

    if campaign.status != "running":
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
    order_ids = pacing.rotate(list(accounts_by_id), campaign.last_account_id)

    destination = None
    if campaign.action in ("add", "invite") and campaign.destination_id:
        destination = await db.get(Destination, campaign.destination_id)

    # Due, queued targets (scheduled_at <= now).
    due_result = await db.execute(
        select(CampaignTarget)
        .where(
            CampaignTarget.campaign_id == campaign.id,
            CampaignTarget.result == "queued",
        )
        .order_by(CampaignTarget.scheduled_at, CampaignTarget.id)
    )
    valid: list[tuple[CampaignTarget, Contact]] = []
    for target in due_result.scalars().all():
        if target.scheduled_at is not None and _as_utc(target.scheduled_at) > now:
            continue
        contact = await db.get(Contact, target.contact_id)
        if contact is None or not contact.consent or contact.opted_out:
            target.result = "skipped"
            summary["skipped"] += 1
        else:
            valid.append((target, contact))

    ti = 0
    for account_id in order_ids:
        if ti >= len(valid):
            break
        account = accounts_by_id[account_id]
        target, contact = valid[ti]
        result = await _execute_target(
            db, campaign, destination, account, target, contact, now, agent_id, rng
        )
        if result.get("warning"):
            account.status = "quarantined"
            campaign.status = "paused"
            summary["paused"] = True
            summary["warning"] = result["warning"]
            break

        state = result.get("result", "failed")
        target.result = state
        target.account_id = account.id
        target.sent_at = now
        target.error = result.get("detail") if state == "failed" else None
        account.actions_today += 1
        account.last_action_at = now
        campaign.last_account_id = account.id
        if state == "sent" and contact.stage == "new":
            contact.stage = "contacted"
            contact.last_contacted_at = now
        summary[state if state in ("sent", "joined") else "failed"] += 1
        summary["actions"].append(
            {"account_id": account.id, "contact_id": contact.id, "result": state}
        )
        ti += 1

    # Complete when nothing is left queued.
    if campaign.status == "running":
        remaining = await db.scalar(
            select(func.count())
            .select_from(CampaignTarget)
            .where(
                CampaignTarget.campaign_id == campaign.id,
                CampaignTarget.result == "queued",
            )
        )
        if not remaining:
            campaign.status = "done"

    await db.commit()
    return summary


# ------------------------------------------------------------------ reports ---


async def ab_report(db: AsyncSession, campaign: Campaign) -> list[dict]:
    """Per-variant (template) result breakdown, including a replied proxy."""
    counts = await db.execute(
        select(CampaignTarget.template_id, CampaignTarget.result, func.count())
        .where(CampaignTarget.campaign_id == campaign.id)
        .group_by(CampaignTarget.template_id, CampaignTarget.result)
    )
    by_template: dict[int | None, dict] = {}
    for template_id, result, count in counts.all():
        by_template.setdefault(template_id, {})[result] = count

    # Replied proxy: targets whose contact reached replied/customer.
    replied = await db.execute(
        select(CampaignTarget.template_id, func.count())
        .join(Contact, Contact.id == CampaignTarget.contact_id)
        .where(
            CampaignTarget.campaign_id == campaign.id,
            Contact.stage.in_(["replied", "customer"]),
        )
        .group_by(CampaignTarget.template_id)
    )
    replied_by = {tid: c for tid, c in replied.all()}

    report = []
    for template_id, results in by_template.items():
        template = await db.get(Template, template_id) if template_id else None
        report.append(
            {
                "template_id": template_id,
                "label": template.variant_label if template else "—",
                "name": template.name if template else "(no template)",
                "queued": results.get("queued", 0),
                "sent": results.get("sent", 0),
                "joined": results.get("joined", 0),
                "failed": results.get("failed", 0),
                "skipped": results.get("skipped", 0),
                "replied": replied_by.get(template_id, 0),
            }
        )
    report.sort(key=lambda r: (r["label"], r["template_id"] or 0))
    return report

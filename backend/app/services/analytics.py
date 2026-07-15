"""Analytics & system-monitoring dashboard.

Two concerns live here:

* :func:`dashboard_snapshot` — live *system* state for the Dashboard (account
  health, sending throughput, queue depth, quarantines, proxy-pool health,
  running campaigns). Broadcast over the inbox WebSocket as a ``dashboard`` event.
* Marketing analytics — :func:`funnel`, :func:`per_source_conversion`,
  :func:`per_account_health`, :func:`campaign_summary`, :func:`utm_attribution`.

All time-window filtering is done in Python (normalising to UTC) so the queries
are portable across PostgreSQL (prod) and SQLite (tests).
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.account import Account
from app.db.models.bot import BotSubscriber
from app.db.models.campaign import Campaign, CampaignTarget
from app.db.models.contact import Contact
from app.db.models.event import Event
from app.db.models.inbox import Message
from app.db.models.proxy import Proxy
from app.db.models.sender import SendTarget
from app.services import referrals as referral_service

# Contact pipeline order used by the funnel & per-source breakdown.
FUNNEL_STAGES = ["new", "contacted", "replied", "joined", "customer", "opted_out"]
ACCOUNT_STATUSES = ["active", "warming", "quarantined", "banned", "logged_out"]
PROXY_HEALTHS = ["ok", "dead", "unknown"]

# Event types surfaced in the Dashboard "recent quarantines & errors" feed.
NOTABLE_EVENT_TYPES = (
    "account.quarantine",
    "account.banned",
    "sender.flood",
    "campaign.flood",
)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


async def _grouped_counts(db: AsyncSession, column) -> dict:
    result = await db.execute(select(column, func.count()).group_by(column))
    return {row[0]: int(row[1]) for row in result.all()}


# --------------------------------------------------------------- dashboard ---


async def _throughput(db: AsyncSession, now: datetime) -> dict:
    """Outgoing message counts today / last hour, filtered in Python (portable)."""
    now = _as_utc(now)
    day_start = now - timedelta(hours=24)
    hour_start = now - timedelta(hours=1)
    result = await db.execute(
        select(Message.created_at)
        .where(Message.direction == "out")
        .order_by(Message.created_at.desc())
        .limit(2000)
    )
    today = last_hour = 0
    for (created_at,) in result.all():
        ts = _as_utc(created_at)
        if ts is None:
            continue
        if ts >= day_start:
            today += 1
        if ts >= hour_start:
            last_hour += 1
    return {"sends_today": today, "sends_last_hour": last_hour}


async def dashboard_snapshot(db: AsyncSession, now: datetime | None = None) -> dict:
    now = _as_utc(now or datetime.now(timezone.utc))

    status_counts = await _grouped_counts(db, Account.status)
    accounts = {s: status_counts.get(s, 0) for s in ACCOUNT_STATUSES}
    accounts["total"] = sum(status_counts.values())

    # Today's sends vs caps (accounts hold a per-day counter reset by ticks).
    cap_row = await db.execute(
        select(func.coalesce(func.sum(Account.actions_today), 0), func.coalesce(func.sum(Account.daily_cap), 0))
    )
    actions_today, daily_cap = cap_row.one()
    caps = {
        "actions_today": int(actions_today or 0),
        "daily_cap": int(daily_cap or 0),
        "pct": round(100 * int(actions_today or 0) / int(daily_cap), 1) if daily_cap else 0.0,
    }

    # Queue depth: work still waiting across the sender and campaigns.
    send_queue = await db.scalar(
        select(func.count()).select_from(SendTarget).where(SendTarget.status == "queued")
    )
    campaign_queue = await db.scalar(
        select(func.count()).select_from(CampaignTarget).where(CampaignTarget.result == "queued")
    )
    queue = {
        "send_targets": int(send_queue or 0),
        "campaign_targets": int(campaign_queue or 0),
        "total": int(send_queue or 0) + int(campaign_queue or 0),
    }

    # Proxy-pool health.
    proxy_health = await _grouped_counts(db, Proxy.health)
    total_proxies = sum(proxy_health.values())
    assigned = await db.scalar(
        select(func.count()).select_from(Proxy).where(Proxy.assigned_account_id.isnot(None))
    )
    proxies = {h: proxy_health.get(h, 0) for h in PROXY_HEALTHS}
    proxies["total"] = total_proxies
    proxies["assigned"] = int(assigned or 0)
    proxies["free"] = total_proxies - int(assigned or 0)

    throughput = await _throughput(db, now)

    # Running campaigns at a glance (with per-campaign progress).
    running_rows = await db.execute(
        select(Campaign).where(Campaign.status == "running").order_by(Campaign.id)
    )
    running = []
    for campaign in running_rows.scalars().all():
        result_counts = await db.execute(
            select(CampaignTarget.result, func.count())
            .where(CampaignTarget.campaign_id == campaign.id)
            .group_by(CampaignTarget.result)
        )
        by_result = {r: int(c) for r, c in result_counts.all()}
        total = sum(by_result.values())
        done = total - by_result.get("queued", 0)
        running.append(
            {
                "id": campaign.id,
                "name": campaign.name,
                "action": campaign.action,
                "total": total,
                "done": done,
                "sent": by_result.get("sent", 0),
                "joined": by_result.get("joined", 0),
                "failed": by_result.get("failed", 0),
            }
        )

    # Recent quarantines & errors.
    events_rows = await db.execute(
        select(Event)
        .where(Event.type.in_(NOTABLE_EVENT_TYPES))
        .order_by(Event.created_at.desc(), Event.id.desc())
        .limit(8)
    )
    recent_events = [
        {
            "id": e.id,
            "type": e.type,
            "entity_ref": e.entity_ref,
            "meta": e.meta or {},
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events_rows.scalars().all()
    ]

    return {
        "generated_at": now.isoformat(),
        "accounts": accounts,
        "caps": caps,
        "queue": queue,
        "proxies": proxies,
        "throughput": throughput,
        "running_campaigns": running,
        "recent_events": recent_events,
    }


# --------------------------------------------------------- marketing stats ---


async def funnel(db: AsyncSession) -> dict:
    """Contact counts per pipeline stage + the contacted→customer conversion."""
    counts = await _grouped_counts(db, Contact.stage)
    stages = {s: counts.get(s, 0) for s in FUNNEL_STAGES}
    total = sum(counts.values())
    # Reached-stage funnel: a contact at 'customer' also passed 'contacted' etc.
    order = ["contacted", "replied", "joined", "customer"]
    cumulative_rank = {s: i for i, s in enumerate(FUNNEL_STAGES)}
    reached = {}
    for target in order:
        tr = cumulative_rank[target]
        reached[target] = sum(
            c for s, c in counts.items()
            # opted_out contacts left the funnel; don't credit them upward.
            if s != "opted_out" and cumulative_rank.get(s, -1) >= tr
        )
    contacted = reached.get("contacted", 0)
    return {
        "total": total,
        "stages": stages,
        "reached": reached,
        "conversion_pct": round(100 * reached.get("customer", 0) / contacted, 1) if contacted else 0.0,
    }


async def per_source_conversion(db: AsyncSession) -> list[dict]:
    """Per-source breakdown of contacts by stage, with a conversion rate."""
    result = await db.execute(
        select(Contact.source, Contact.stage, func.count())
        .group_by(Contact.source, Contact.stage)
    )
    by_source: dict[str, dict] = {}
    for source, stage, count in result.all():
        key = source or "(none)"
        row = by_source.setdefault(
            key, {"source": key, "total": 0, **{s: 0 for s in FUNNEL_STAGES}}
        )
        row[stage] = row.get(stage, 0) + int(count)
        row["total"] += int(count)
    rows = list(by_source.values())
    for row in rows:
        customers = row.get("customer", 0)
        row["conversion_pct"] = round(100 * customers / row["total"], 1) if row["total"] else 0.0
    rows.sort(key=lambda r: (-r["total"], r["source"]))
    return rows


async def per_account_health(db: AsyncSession) -> list[dict]:
    result = await db.execute(select(Account).order_by(Account.id))
    return [
        {
            "id": a.id,
            "label": a.label,
            "status": a.status,
            "spam_state": a.spam_state,
            "warmup_stage": a.warmup_stage,
            "actions_today": a.actions_today,
            "daily_cap": a.daily_cap,
            "logged_in": a.session_ref is not None,
            "last_action_at": a.last_action_at.isoformat() if a.last_action_at else None,
        }
        for a in result.scalars().all()
    ]


async def campaign_summary(db: AsyncSession) -> list[dict]:
    """All campaigns with target-result rollups (campaign + A/B performance)."""
    campaigns_rows = await db.execute(select(Campaign).order_by(Campaign.created_at.desc()))
    counts = await db.execute(
        select(CampaignTarget.campaign_id, CampaignTarget.result, func.count())
        .group_by(CampaignTarget.campaign_id, CampaignTarget.result)
    )
    by_campaign: dict[int, dict] = {}
    for campaign_id, result, count in counts.all():
        by_campaign.setdefault(campaign_id, {})[result] = int(count)
    rows = []
    for campaign in campaigns_rows.scalars().all():
        c = by_campaign.get(campaign.id, {})
        rows.append(
            {
                "id": campaign.id,
                "name": campaign.name,
                "action": campaign.action,
                "status": campaign.status,
                "ab_test": campaign.ab_test,
                "targets": sum(c.values()),
                "sent": c.get("sent", 0),
                "joined": c.get("joined", 0),
                "replied": c.get("replied", 0),
                "failed": c.get("failed", 0),
                "queued": c.get("queued", 0),
            }
        )
    return rows


async def utm_attribution(db: AsyncSession) -> list[dict]:
    """Bot subscribers grouped by UTM deep-link source, with conversions."""
    result = await db.execute(
        select(BotSubscriber, Contact.stage)
        .join(Contact, Contact.id == BotSubscriber.contact_id, isouter=True)
    )
    by_utm: dict[str, dict] = {}
    for subscriber, stage in result.all():
        key = subscriber.utm_source or "(direct)"
        row = by_utm.setdefault(
            key, {"utm_source": key, "subscribers": 0, "subscribed": 0, "converted": 0}
        )
        row["subscribers"] += 1
        if subscriber.is_subscribed:
            row["subscribed"] += 1
        if stage in ("joined", "customer"):
            row["converted"] += 1
    rows = list(by_utm.values())
    rows.sort(key=lambda r: (-r["subscribers"], r["utm_source"]))
    return rows


async def analytics_overview(db: AsyncSession) -> dict:
    return {
        "funnel": await funnel(db),
        "per_source": await per_source_conversion(db),
        "per_account": await per_account_health(db),
        "campaigns": await campaign_summary(db),
        "utm": await utm_attribution(db),
        "referrals": await referral_service.leaderboard(db),
    }

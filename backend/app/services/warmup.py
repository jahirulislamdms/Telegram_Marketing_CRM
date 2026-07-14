"""Warmup orchestration: runs, participants/partners, staged ramp, and the tick.

The ``run_tick`` coroutine advances stages on schedule and performs one paced
action per eligible participant (join a group, or chit-chat a fleet peer /
external partner). Telegram side effects are delegated via the injected
``execute`` callable so the logic is testable without a live account.
"""

from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.models.account import Account
from app.db.models.warmup import WarmupParticipant, WarmupPartner, WarmupRun

# Default staged ramp (mirrors spec §7). Copied onto a run at creation; editable.
DEFAULT_STAGES = [
    {"days": 3, "max_actions": 2},
    {"days": 4, "max_actions": 5},
    {"days": 5, "max_actions": 12},
]

# execute(participant, account, action) -> None ; raises on failure.
ExecuteFn = Callable[[WarmupParticipant, Account, dict], Awaitable[None]]


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def stage_cap(stages: list, stage: int, full_cap: int) -> int:
    if 0 <= stage < len(stages):
        return int(stages[stage].get("max_actions", full_cap))
    return full_cap


def stage_progress(stage: int, stages: list) -> str:
    total = len(stages) or 1
    return f"{min(stage + 1, total)}/{total}"


# --------------------------------------------------------------------- CRUD ---


async def list_runs(db: AsyncSession) -> list[WarmupRun]:
    result = await db.execute(select(WarmupRun).order_by(WarmupRun.created_at.desc()))
    return list(result.scalars().all())


async def get_run(db: AsyncSession, run_id: int) -> WarmupRun | None:
    return await db.get(WarmupRun, run_id)


async def create_run(
    db: AsyncSession,
    *,
    name: str,
    groups: list[str],
    messages: list[str],
    stages: list | None,
    min_delay_seconds: int,
    max_delay_seconds: int,
    created_by: int | None,
) -> WarmupRun:
    run = WarmupRun(
        name=name,
        groups=groups,
        messages=messages,
        stages=stages or DEFAULT_STAGES,
        min_delay_seconds=min_delay_seconds,
        max_delay_seconds=max_delay_seconds,
        created_by=created_by,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)
    return run


async def get_participants(db: AsyncSession, run_id: int) -> list[WarmupParticipant]:
    result = await db.execute(
        select(WarmupParticipant)
        .where(WarmupParticipant.run_id == run_id)
        .order_by(WarmupParticipant.id)
    )
    return list(result.scalars().all())


async def get_partners(db: AsyncSession, run_id: int) -> list[WarmupPartner]:
    result = await db.execute(
        select(WarmupPartner)
        .where(WarmupPartner.run_id == run_id)
        .order_by(WarmupPartner.id)
    )
    return list(result.scalars().all())


async def add_participants(
    db: AsyncSession, run: WarmupRun, account_ids: list[int]
) -> list[WarmupParticipant]:
    existing = {p.account_id for p in await get_participants(db, run.id)}
    created = []
    for account_id in account_ids:
        if account_id in existing:
            continue
        account = await db.get(Account, account_id)
        if account is None:
            continue
        participant = WarmupParticipant(
            run_id=run.id,
            account_id=account_id,
            status="active" if run.status == "running" else "pending",
            stage_started_at=datetime.now(timezone.utc) if run.status == "running" else None,
        )
        db.add(participant)
        created.append(participant)
    await db.commit()
    for p in created:
        await db.refresh(p)
    return created


async def remove_participant(db: AsyncSession, participant: WarmupParticipant) -> None:
    await db.delete(participant)
    await db.commit()


async def add_partner(
    db: AsyncSession, run: WarmupRun, identifier: str, kind: str
) -> WarmupPartner:
    partner = WarmupPartner(run_id=run.id, identifier=identifier, kind=kind)
    db.add(partner)
    await db.commit()
    await db.refresh(partner)
    return partner


async def remove_partner(db: AsyncSession, partner: WarmupPartner) -> None:
    await db.delete(partner)
    await db.commit()


# ---------------------------------------------------------------- lifecycle ---


async def start_run(db: AsyncSession, run: WarmupRun) -> WarmupRun:
    now = datetime.now(timezone.utc)
    run.status = "running"
    if run.started_at is None:
        run.started_at = now
    for participant in await get_participants(db, run.id):
        if participant.status in ("pending", "paused"):
            participant.status = "active"
            if participant.stage_started_at is None:
                participant.stage_started_at = now
            account = await db.get(Account, participant.account_id)
            if account is not None:
                account.status = "warming"
                account.warmup_stage = participant.stage
                if account.warmup_started_at is None:
                    account.warmup_started_at = now
    await db.commit()
    await db.refresh(run)
    return run


async def pause_run(db: AsyncSession, run: WarmupRun) -> WarmupRun:
    run.status = "paused"
    await db.commit()
    await db.refresh(run)
    return run


async def stop_run(db: AsyncSession, run: WarmupRun) -> WarmupRun:
    run.status = "done"
    for participant in await get_participants(db, run.id):
        participant.status = "done"
        account = await db.get(Account, participant.account_id)
        if account is not None and account.status == "warming":
            account.status = "active"
    await db.commit()
    await db.refresh(run)
    return run


# --------------------------------------------------------------------- tick ---


def _choose_action(
    participant: WarmupParticipant,
    account: Account,
    run: WarmupRun,
    peers: list[Account],
    partners: list[WarmupPartner],
) -> dict | None:
    joined = list(participant.joined or [])
    remaining = [g for g in (run.groups or []) if g not in joined]
    if remaining:
        return {"type": "join", "link": remaining[0]}

    if not run.messages:
        return None

    targets: list[str] = [p.identifier for p in partners]
    targets += [a.phone for a in peers if a.id != account.id and a.phone]
    if not targets:
        return None

    target = targets[participant.actions_today % len(targets)]
    text = run.messages[participant.actions_today % len(run.messages)]
    return {"type": "send", "target": target, "text": text}


async def run_tick(
    db: AsyncSession,
    run: WarmupRun,
    now: datetime,
    execute: ExecuteFn,
) -> dict:
    """Advance stages and perform one paced action per eligible participant."""
    now = _as_utc(now)
    stages = run.stages or DEFAULT_STAGES
    today = now.strftime("%Y-%m-%d")

    participants = [
        p for p in await get_participants(db, run.id) if p.status == "active"
    ]
    accounts = {p.id: await db.get(Account, p.account_id) for p in participants}
    peer_accounts = [a for a in accounts.values() if a is not None]
    partners = await get_partners(db, run.id)

    summary = {"advanced": 0, "completed": 0, "actions": [], "errors": []}

    for participant in participants:
        account = accounts[participant.id]
        if account is None:
            continue

        # Daily counter reset.
        if participant.day_key != today:
            participant.actions_today = 0
            participant.day_key = today

        # Stage advancement / completion.
        started = _as_utc(participant.stage_started_at) or now
        if participant.stage_started_at is None:
            participant.stage_started_at = now
        stage_days = stages[participant.stage]["days"] if participant.stage < len(stages) else 0
        if (now - started) >= timedelta(days=stage_days):
            if participant.stage < len(stages) - 1:
                participant.stage += 1
                participant.stage_started_at = now
                account.warmup_stage = participant.stage
                summary["advanced"] += 1
            else:
                # Final stage duration elapsed -> warmup complete.
                participant.status = "done"
                if account.status == "warming":
                    account.status = "active"
                summary["completed"] += 1
                continue

        # Paced action.
        cap = stage_cap(stages, participant.stage, settings_full_cap())
        last = _as_utc(participant.last_action_at)
        delay_ok = last is None or (now - last) >= timedelta(
            seconds=run.min_delay_seconds
        )
        if participant.actions_today >= cap or not delay_ok:
            continue

        action = _choose_action(participant, account, run, peer_accounts, partners)
        if action is None:
            continue

        try:
            await execute(participant, account, action)
        except Exception as exc:  # noqa: BLE001
            summary["errors"].append({"account_id": account.id, "error": str(exc)})
            continue

        participant.actions_today += 1
        participant.last_action_at = now
        if action["type"] == "join":
            participant.joined = joined_with(participant, action["link"])
        summary["actions"].append(
            {"account_id": account.id, "type": action["type"], **_action_meta(action)}
        )

    await db.commit()
    return summary


def joined_with(participant: WarmupParticipant, link: str) -> list:
    return list(participant.joined or []) + [link]


def _action_meta(action: dict) -> dict:
    if action["type"] == "join":
        return {"link": action["link"]}
    return {"target": action["target"]}


def settings_full_cap() -> int:
    return getattr(settings, "warmup_full_daily_cap", 30)

"""Warmup endpoints (Admin/Manager): runs, participants, partners, and the tick."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_manager
from app.db.models.proxy import Proxy
from app.db.models.user import User
from app.db.models.warmup import WarmupParticipant
from app.db.session import get_db
from app.schemas.warmup import (
    AddPartner,
    AddParticipants,
    ParticipantOut,
    PartnerOut,
    TickResult,
    WarmupRunCreate,
    WarmupRunDetail,
    WarmupRunOut,
)
from app.services import accounts as account_service
from app.services import audit
from app.services import engine_client
from app.services import warmup as warmup_service

router = APIRouter(prefix="/warmup", tags=["warmup"])


async def _get_run_or_404(db: AsyncSession, run_id: int):
    run = await warmup_service.get_run(db, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found")
    return run


async def _build_detail(db: AsyncSession, run) -> WarmupRunDetail:
    stages = run.stages or warmup_service.DEFAULT_STAGES
    participants = await warmup_service.get_participants(db, run.id)
    partners = await warmup_service.get_partners(db, run.id)
    p_out = []
    for p in participants:
        account = await account_service.get_by_id(db, p.account_id)
        p_out.append(
            ParticipantOut(
                id=p.id,
                account_id=p.account_id,
                account_label=account.label if account else f"#{p.account_id}",
                stage=p.stage,
                stage_progress=warmup_service.stage_progress(p.stage, stages),
                actions_today=p.actions_today,
                status=p.status,
                last_action_at=p.last_action_at,
                joined=p.joined or [],
            )
        )
    return WarmupRunDetail(
        **WarmupRunOut.model_validate(run).model_dump(),
        participants=p_out,
        partners=[PartnerOut.model_validate(x) for x in partners],
    )


@router.get("/runs", response_model=list[WarmupRunOut])
async def list_runs(
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await warmup_service.list_runs(db)


@router.post("/runs", response_model=WarmupRunOut, status_code=status.HTTP_201_CREATED)
async def create_run(
    payload: WarmupRunCreate,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> WarmupRunOut:
    run = await warmup_service.create_run(
        db,
        name=payload.name,
        groups=payload.groups,
        messages=payload.messages,
        stages=[s.model_dump() for s in payload.stages] if payload.stages else None,
        min_delay_seconds=payload.min_delay_seconds,
        max_delay_seconds=payload.max_delay_seconds,
        created_by=user.id,
    )
    await audit.record_event(
        db,
        type="warmup.create",
        actor_type="user",
        actor_id=user.id,
        entity_ref=f"warmup:{run.id}",
        meta={"name": run.name},
    )
    return run


@router.get("/runs/{run_id}", response_model=WarmupRunDetail)
async def get_run(
    run_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> WarmupRunDetail:
    run = await _get_run_or_404(db, run_id)
    return await _build_detail(db, run)


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_run(
    run_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> None:
    run = await _get_run_or_404(db, run_id)
    await db.delete(run)
    await db.commit()


@router.post("/runs/{run_id}/participants", response_model=WarmupRunDetail)
async def add_participants(
    run_id: int,
    payload: AddParticipants,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> WarmupRunDetail:
    run = await _get_run_or_404(db, run_id)
    await warmup_service.add_participants(db, run, payload.account_ids)
    return await _build_detail(db, run)


@router.delete("/runs/{run_id}/participants/{participant_id}", response_model=WarmupRunDetail)
async def remove_participant(
    run_id: int,
    participant_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> WarmupRunDetail:
    run = await _get_run_or_404(db, run_id)
    participant = await db.get(WarmupParticipant, participant_id)
    if participant is not None and participant.run_id == run_id:
        await warmup_service.remove_participant(db, participant)
    return await _build_detail(db, run)


@router.post("/runs/{run_id}/partners", response_model=WarmupRunDetail)
async def add_partner(
    run_id: int,
    payload: AddPartner,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> WarmupRunDetail:
    run = await _get_run_or_404(db, run_id)
    await warmup_service.add_partner(db, run, payload.identifier, payload.kind)
    return await _build_detail(db, run)


@router.post("/runs/{run_id}/start", response_model=WarmupRunDetail)
async def start_run(
    run_id: int,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> WarmupRunDetail:
    run = await _get_run_or_404(db, run_id)
    await warmup_service.start_run(db, run)
    await audit.record_event(
        db,
        type="warmup.start",
        actor_type="user",
        actor_id=user.id,
        entity_ref=f"warmup:{run.id}",
    )
    return await _build_detail(db, run)


@router.post("/runs/{run_id}/pause", response_model=WarmupRunDetail)
async def pause_run(
    run_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> WarmupRunDetail:
    run = await _get_run_or_404(db, run_id)
    await warmup_service.pause_run(db, run)
    return await _build_detail(db, run)


@router.post("/runs/{run_id}/stop", response_model=WarmupRunDetail)
async def stop_run(
    run_id: int,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> WarmupRunDetail:
    run = await _get_run_or_404(db, run_id)
    await warmup_service.stop_run(db, run)
    await audit.record_event(
        db,
        type="warmup.stop",
        actor_type="user",
        actor_id=user.id,
        entity_ref=f"warmup:{run.id}",
    )
    return await _build_detail(db, run)


@router.post("/runs/{run_id}/tick", response_model=TickResult)
async def tick(
    run_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> TickResult:
    """Run one orchestration tick (also invoked periodically by Celery beat)."""
    run = await _get_run_or_404(db, run_id)
    if run.status != "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Run is not running"
        )

    async def _execute(participant, account, action) -> None:
        proxy = (
            await db.get(Proxy, account.proxy_id) if account.proxy_id else None
        )
        if action["type"] == "join":
            await engine_client.warmup_join(account, proxy, action["link"])
        else:
            result = await engine_client.warmup_send(
                account, proxy, action["target"], action["text"]
            )
            if not result.get("sent", True):
                raise engine_client.EngineUnavailable(
                    f"warmup send failed: {result.get('error')}"
                )

    summary = await warmup_service.run_tick(
        db, run, datetime.now(timezone.utc), _execute
    )
    return TickResult(**summary)

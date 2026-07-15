"""Sender endpoints (Admin/Manager): send jobs, targets, and the paced tick."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_manager
from app.db.models.contact import Contact
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.sender import (
    AddTargets,
    SendJobCreate,
    SendJobDetail,
    SendJobOut,
    TargetOut,
    TickResult,
)
from app.services import audit
from app.services import sender as sender_service

router = APIRouter(prefix="/sender", tags=["sender"])


async def _get_job_or_404(db: AsyncSession, job_id: int):
    job = await sender_service.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return job


async def _build_detail(db: AsyncSession, job) -> SendJobDetail:
    targets = await sender_service.get_targets(db, job.id)
    stats = await sender_service.target_stats(db, job.id)
    t_out = []
    for t in targets:
        contact = await db.get(Contact, t.contact_id)
        t_out.append(
            TargetOut(
                id=t.id,
                contact_id=t.contact_id,
                contact_label=contact.display_label if contact else f"#{t.contact_id}",
                account_id=t.account_id,
                status=t.status,
                error=t.error,
                rendered_body=t.rendered_body,
            )
        )
    return SendJobDetail(
        **SendJobOut.model_validate(job).model_dump(), stats=stats, targets=t_out
    )


@router.get("/jobs", response_model=list[SendJobOut])
async def list_jobs(
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await sender_service.list_jobs(db)


@router.post("/jobs", response_model=SendJobOut, status_code=status.HTTP_201_CREATED)
async def create_job(
    payload: SendJobCreate,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> SendJobOut:
    job = await sender_service.create_job(
        db,
        name=payload.name,
        template=payload.template,
        include_link=payload.include_link,
        link_url=payload.link_url,
        suppress_link_first=payload.suppress_link_first,
        created_by=user.id,
    )
    await audit.record_event(
        db,
        type="sender.create",
        actor_type="user",
        actor_id=user.id,
        entity_ref=f"sendjob:{job.id}",
    )
    return job


@router.get("/jobs/{job_id}", response_model=SendJobDetail)
async def get_job(
    job_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> SendJobDetail:
    job = await _get_job_or_404(db, job_id)
    return await _build_detail(db, job)


@router.post("/jobs/{job_id}/targets", response_model=SendJobDetail)
async def add_targets(
    job_id: int,
    payload: AddTargets,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> SendJobDetail:
    job = await _get_job_or_404(db, job_id)
    await sender_service.add_targets(
        db, job, contact_ids=payload.contact_ids, source=payload.source
    )
    return await _build_detail(db, job)


@router.post("/jobs/{job_id}/start", response_model=SendJobDetail)
async def start_job(
    job_id: int,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> SendJobDetail:
    job = await _get_job_or_404(db, job_id)
    await sender_service.start_job(db, job)
    await audit.record_event(
        db, type="sender.start", actor_type="user", actor_id=user.id,
        entity_ref=f"sendjob:{job.id}",
    )
    return await _build_detail(db, job)


@router.post("/jobs/{job_id}/pause", response_model=SendJobDetail)
async def pause_job(
    job_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> SendJobDetail:
    job = await _get_job_or_404(db, job_id)
    await sender_service.pause_job(db, job)
    return await _build_detail(db, job)


@router.post("/jobs/{job_id}/stop", response_model=SendJobDetail)
async def stop_job(
    job_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> SendJobDetail:
    job = await _get_job_or_404(db, job_id)
    await sender_service.stop_job(db, job)
    return await _build_detail(db, job)


@router.post("/jobs/{job_id}/tick", response_model=TickResult)
async def tick(
    job_id: int,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> TickResult:
    job = await _get_job_or_404(db, job_id)
    if job.status != "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Job is not running"
        )

    executor = sender_service.build_executor(db, user.id)
    summary = await sender_service.run_tick(
        db, job, datetime.now(timezone.utc), executor
    )
    if summary.get("paused"):
        await audit.record_event(
            db,
            type="sender.autopause",
            actor_type="system",
            entity_ref=f"sendjob:{job.id}",
            meta={"warning": summary.get("warning")},
        )
    return TickResult(**summary)

"""Templates & campaigns endpoints (Admin/Manager)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_manager
from app.db.models.contact import Contact
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.campaign import (
    CampaignCreate,
    CampaignDetail,
    CampaignOut,
    CampaignTargetOut,
    CampaignTickResult,
    TemplateCreate,
    TemplateOut,
)
from app.services import audit
from app.services import campaigns as campaign_service

router = APIRouter(tags=["campaigns"])


# ------------------------------------------------------------- templates -----


@router.get("/templates", response_model=list[TemplateOut])
async def list_templates(
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await campaign_service.list_templates(db)


@router.post("/templates", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(
    payload: TemplateCreate,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> TemplateOut:
    return await campaign_service.create_template(
        db,
        name=payload.name,
        body=payload.body,
        include_link=payload.include_link,
        link_url=payload.link_url,
        variant_group=payload.variant_group,
        variant_label=payload.variant_label,
        created_by=user.id,
    )


# ------------------------------------------------------------- campaigns -----


async def _get_campaign_or_404(db: AsyncSession, campaign_id: int):
    campaign = await campaign_service.get_campaign(db, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Campaign not found")
    return campaign


async def _build_detail(db: AsyncSession, campaign) -> CampaignDetail:
    targets = await campaign_service.get_targets(db, campaign.id)
    stats = {"queued": 0, "sent": 0, "joined": 0, "failed": 0, "skipped": 0, "replied": 0}
    t_out = []
    for t in targets:
        stats[t.result] = stats.get(t.result, 0) + 1
        contact = await db.get(Contact, t.contact_id)
        t_out.append(
            CampaignTargetOut(
                id=t.id,
                contact_id=t.contact_id,
                contact_label=contact.display_label if contact else f"#{t.contact_id}",
                step=t.step,
                template_id=t.template_id,
                account_id=t.account_id,
                result=t.result,
                error=t.error,
            )
        )
    ab = await campaign_service.ab_report(db, campaign)
    return CampaignDetail(
        **CampaignOut.model_validate(campaign).model_dump(),
        stats=stats,
        ab_report=ab,
        targets=t_out,
    )


@router.get("/campaigns", response_model=list[CampaignOut])
async def list_campaigns(
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await campaign_service.list_campaigns(db)


@router.post("/campaigns", response_model=CampaignOut, status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> CampaignOut:
    if payload.action in ("add", "invite") and payload.destination_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="destination_id is required for add/invite campaigns",
        )
    if payload.action == "message" and not all(s.variant_group for s in payload.steps):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="each step needs a variant_group for message campaigns",
        )
    campaign = await campaign_service.create_campaign(
        db,
        name=payload.name,
        action=payload.action,
        destination_id=payload.destination_id,
        segment=payload.segment.model_dump(exclude_none=True),
        steps=[s.model_dump() for s in payload.steps],
        ab_test=payload.ab_test,
        created_by=user.id,
    )
    await audit.record_event(
        db, type="campaign.create", actor_type="user", actor_id=user.id,
        entity_ref=f"campaign:{campaign.id}",
    )
    return campaign


@router.get("/campaigns/{campaign_id}", response_model=CampaignDetail)
async def get_campaign(
    campaign_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> CampaignDetail:
    campaign = await _get_campaign_or_404(db, campaign_id)
    return await _build_detail(db, campaign)


@router.post("/campaigns/{campaign_id}/start", response_model=CampaignDetail)
async def start_campaign(
    campaign_id: int,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> CampaignDetail:
    campaign = await _get_campaign_or_404(db, campaign_id)
    await campaign_service.start_campaign(db, campaign, datetime.now(timezone.utc))
    await audit.record_event(
        db, type="campaign.start", actor_type="user", actor_id=user.id,
        entity_ref=f"campaign:{campaign.id}",
    )
    return await _build_detail(db, campaign)


@router.post("/campaigns/{campaign_id}/pause", response_model=CampaignDetail)
async def pause_campaign(
    campaign_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> CampaignDetail:
    campaign = await _get_campaign_or_404(db, campaign_id)
    await campaign_service.pause_campaign(db, campaign)
    return await _build_detail(db, campaign)


@router.post("/campaigns/{campaign_id}/stop", response_model=CampaignDetail)
async def stop_campaign(
    campaign_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> CampaignDetail:
    campaign = await _get_campaign_or_404(db, campaign_id)
    await campaign_service.stop_campaign(db, campaign)
    return await _build_detail(db, campaign)


@router.post("/campaigns/{campaign_id}/tick", response_model=CampaignTickResult)
async def tick(
    campaign_id: int,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> CampaignTickResult:
    campaign = await _get_campaign_or_404(db, campaign_id)
    if campaign.status != "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Campaign is not running"
        )
    summary = await campaign_service.run_tick(
        db, campaign, datetime.now(timezone.utc), agent_id=user.id
    )
    return CampaignTickResult(
        sent=summary["sent"],
        joined=summary["joined"],
        failed=summary["failed"],
        skipped=summary["skipped"],
        paused=summary["paused"],
        actions=summary["actions"],
        warning=summary.get("warning"),
    )

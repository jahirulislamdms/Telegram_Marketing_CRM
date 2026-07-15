"""Dashboard, marketing analytics, and referral endpoints (Admin/Manager)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_manager
from app.db.models.bot import Bot, BotSubscriber
from app.db.models.user import User
from app.db.session import get_db
from app.realtime import publish
from app.schemas.analytics import (
    AnalyticsOverview,
    CreateReferralRequest,
    DashboardSnapshot,
    RecordReferralRequest,
    ReferralDetail,
    ReferralOut,
    RewardRequest,
)
from app.services import analytics as analytics_service
from app.services import audit
from app.services import bots as bot_service
from app.services import referrals as referral_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


# ------------------------------------------------------------- dashboard -----


@router.get("/dashboard", response_model=DashboardSnapshot)
async def get_dashboard(
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> DashboardSnapshot:
    snapshot = await analytics_service.dashboard_snapshot(db, datetime.now(timezone.utc))
    return DashboardSnapshot(**snapshot)


@router.post("/dashboard/broadcast", response_model=DashboardSnapshot)
async def broadcast_dashboard(
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> DashboardSnapshot:
    """Compute a snapshot and push it over the inbox WebSocket as a ``dashboard``
    event. Called by the Celery beat task in prod; also usable manually."""
    snapshot = await analytics_service.dashboard_snapshot(db, datetime.now(timezone.utc))
    await publish({"type": "dashboard", "snapshot": snapshot})
    return DashboardSnapshot(**snapshot)


# ------------------------------------------------------------- analytics -----


@router.get("", response_model=AnalyticsOverview)
async def get_analytics(
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> AnalyticsOverview:
    return AnalyticsOverview(**await analytics_service.analytics_overview(db))


# ------------------------------------------------------------- referrals -----


async def _referral_detail(db: AsyncSession, referral) -> ReferralDetail:
    subscriber = await db.get(BotSubscriber, referral.referrer_subscriber_id)
    bot = await db.get(Bot, subscriber.bot_id) if subscriber else None
    payload = referral_service.deep_link_payload(referral)
    deep_link = bot_service.deep_link(bot, payload) if bot else f"?start={payload}"
    return ReferralDetail(**ReferralOut.model_validate(referral).model_dump(), deep_link=deep_link)


@router.get("/referrals")
async def referral_leaderboard(
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await referral_service.leaderboard(db)


@router.post("/referrals", response_model=ReferralDetail, status_code=status.HTTP_201_CREATED)
async def create_referral(
    payload: CreateReferralRequest,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> ReferralDetail:
    subscriber = await db.get(BotSubscriber, payload.subscriber_id)
    if subscriber is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Subscriber not found")
    referral = await referral_service.get_or_create_referral(db, subscriber.id)
    return await _referral_detail(db, referral)


@router.post("/referrals/record", response_model=ReferralOut)
async def record_referral(
    payload: RecordReferralRequest,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> ReferralOut:
    referral = await referral_service.record_referral(db, payload.invite_code)
    if referral is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown invite code")
    await audit.record_event(
        db, type="referral.record", actor_type="user", actor_id=user.id,
        entity_ref=f"referral:{referral.id}",
    )
    return referral


@router.post("/referrals/{referral_id}/reward", response_model=ReferralOut)
async def reward_referral(
    referral_id: int,
    payload: RewardRequest,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> ReferralOut:
    referral = await referral_service.get_referral(db, referral_id)
    if referral is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Referral not found")
    await referral_service.set_rewarded(db, referral, payload.rewarded)
    await audit.record_event(
        db, type="referral.reward", actor_type="user", actor_id=user.id,
        entity_ref=f"referral:{referral.id}",
    )
    return referral

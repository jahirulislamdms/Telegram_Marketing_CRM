"""Audit-log endpoint (Admin only)."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.event import EventOut
from app.services import audit

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("", response_model=list[EventOut])
async def list_audit(
    limit: int = Query(default=100, ge=1, le=500),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await audit.list_events(db, limit=limit)

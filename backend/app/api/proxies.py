"""Proxy pool endpoints (Admin/Manager)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_manager
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.proxy import ProxyImportRequest, ProxyImportResult, ProxyOut
from app.services import audit
from app.services import proxies as proxy_service

router = APIRouter(prefix="/proxies", tags=["proxies"])


@router.get("", response_model=list[ProxyOut])
async def list_proxies(
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await proxy_service.list_proxies(db)


@router.post("/import", response_model=ProxyImportResult)
async def import_proxies(
    payload: ProxyImportRequest,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> ProxyImportResult:
    result = await proxy_service.import_proxies(db, payload.raw)
    await audit.record_event(
        db,
        type="proxy.import",
        actor_type="user",
        actor_id=user.id,
        meta={"imported": result["imported"], "skipped": result["skipped_duplicates"]},
    )
    return ProxyImportResult(**result)

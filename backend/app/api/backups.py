"""Backup & Restore center endpoints (§15.2) — Admin only.

Archives contain Telethon session files and full database data, so every route
here requires an admin and is served over HTTPS only (see docs/DEPLOY.md).
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.backup import (
    BackupOut,
    BackupSettingsIn,
    BackupSettingsOut,
    CreateBackup,
    RestoreResult,
)
from app.services import audit
from app.services import backup as backup_service

router = APIRouter(prefix="/backups", tags=["backups"])
log = logging.getLogger("api.backups")


def _bad(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)


@router.get("", response_model=list[BackupOut])
async def list_backups(_: User = Depends(require_admin)) -> list:
    return backup_service.list_backups()


@router.post("", response_model=BackupOut, status_code=status.HTTP_201_CREATED)
async def create_backup(
    payload: CreateBackup,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    try:
        meta = await backup_service.create_backup(db, payload.scope or None)
    except Exception as exc:  # noqa: BLE001
        log.exception("backup failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Backup failed: {exc}"
        )
    await audit.record_event(
        db, type="backup.create", actor_type="user", actor_id=user.id,
        entity_ref=f"backup:{meta['name']}", meta={"scope": meta["scope"]},
    )
    return meta


@router.get("/settings", response_model=BackupSettingsOut)
async def get_settings(
    _: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> dict:
    return await backup_service.get_backup_settings(db)


@router.put("/settings", response_model=BackupSettingsOut)
async def update_settings(
    payload: BackupSettingsIn,
    user: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    cfg = await backup_service.set_backup_settings(
        db, enabled=payload.enabled, interval_days=payload.interval_days, scope=payload.scope
    )
    await audit.record_event(
        db, type="backup.settings", actor_type="user", actor_id=user.id, meta=cfg
    )
    return cfg


@router.get("/{name}/download")
async def download_backup(name: str, _: User = Depends(require_admin)) -> FileResponse:
    try:
        archive = backup_service.resolve_archive(name)
    except ValueError as exc:
        raise _bad(str(exc))
    if not archive.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    return FileResponse(
        path=str(archive), media_type="application/gzip", filename=archive.name
    )


@router.delete("/{name}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_backup(
    name: str, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> None:
    try:
        backup_service.delete_backup(name)
    except ValueError as exc:
        raise _bad(str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    await audit.record_event(
        db, type="backup.delete", actor_type="user", actor_id=user.id, entity_ref=f"backup:{name}"
    )


@router.post("/{name}/restore", response_model=RestoreResult)
async def restore_backup(
    name: str, user: User = Depends(require_admin), db: AsyncSession = Depends(get_db)
) -> dict:
    """Restore an archive over the running system. Disruptive — the UI confirms first."""
    try:
        result = await backup_service.restore_backup(db, name)
    except ValueError as exc:
        raise _bad(str(exc))
    except FileNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Backup not found")
    except Exception as exc:  # noqa: BLE001
        log.exception("restore failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Restore failed: {exc}"
        )
    await audit.record_event(
        db, type="backup.restore", actor_type="user", actor_id=user.id,
        entity_ref=f"backup:{name}", meta=result,
    )
    return result

"""Groups & Channels ("Add members") endpoints (Admin/Manager)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_manager
from app.db.models.contact import Contact
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.destination import (
    AddMembersRequest,
    AddMembersResult,
    AddTickResult,
    DestinationCreate,
    DestinationDetail,
    DestinationOut,
    MembershipOut,
)
from app.services import audit
from app.services import destinations as dest_service

router = APIRouter(prefix="/destinations", tags=["destinations"])


async def _get_destination_or_404(db: AsyncSession, destination_id: int):
    destination = await dest_service.get_destination(db, destination_id)
    if destination is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Destination not found")
    return destination


async def _build_detail(db: AsyncSession, destination) -> DestinationDetail:
    memberships = await dest_service.get_memberships(db, destination.id)
    stats = {"pending": 0, "added": 0, "invited": 0, "joined": 0, "failed": 0}
    m_out = []
    for m in memberships:
        stats[m.state] = stats.get(m.state, 0) + 1
        contact = await db.get(Contact, m.contact_id)
        m_out.append(
            MembershipOut(
                id=m.id,
                contact_id=m.contact_id,
                contact_label=contact.display_label if contact else f"#{m.contact_id}",
                state=m.state,
                method=m.method,
                account_id=m.account_id,
                error=m.error,
            )
        )
    return DestinationDetail(
        **DestinationOut.model_validate(destination).model_dump(),
        stats=stats,
        memberships=m_out,
    )


@router.get("", response_model=list[DestinationOut])
async def list_destinations(
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> list:
    return await dest_service.list_destinations(db)


@router.post("", response_model=DestinationOut, status_code=status.HTTP_201_CREATED)
async def register_destination(
    payload: DestinationCreate,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> DestinationOut:
    destination = await dest_service.register_destination(db, payload.link)
    await audit.record_event(
        db,
        type="destination.register",
        actor_type="user",
        actor_id=user.id,
        entity_ref=f"destination:{destination.id}",
        meta={"resolved": destination.tg_entity_id is not None},
    )
    return destination


@router.get("/{destination_id}", response_model=DestinationDetail)
async def get_destination(
    destination_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> DestinationDetail:
    destination = await _get_destination_or_404(db, destination_id)
    return await _build_detail(db, destination)


@router.delete("/{destination_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_destination(
    destination_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> None:
    destination = await _get_destination_or_404(db, destination_id)
    await db.delete(destination)
    await db.commit()


@router.post("/{destination_id}/add-members", response_model=AddMembersResult)
async def add_members(
    destination_id: int,
    payload: AddMembersRequest,
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> AddMembersResult:
    destination = await _get_destination_or_404(db, destination_id)
    result = await dest_service.add_members(
        db, destination, contact_ids=payload.contact_ids, identifiers=payload.identifiers
    )
    await audit.record_event(
        db,
        type="destination.add_members",
        actor_type="user",
        actor_id=user.id,
        entity_ref=f"destination:{destination.id}",
        meta=result,
    )
    return AddMembersResult(**result)


@router.post("/{destination_id}/add-members/tick", response_model=AddTickResult)
async def add_members_tick(
    destination_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> AddTickResult:
    destination = await _get_destination_or_404(db, destination_id)
    if destination.tg_entity_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Destination is not resolved yet",
        )
    executor = dest_service.build_add_executor(db)
    summary = await dest_service.run_add_tick(
        db, destination, datetime.now(timezone.utc), executor
    )
    return AddTickResult(
        added=summary["added"],
        invited=summary["invited"],
        failed=summary["failed"],
        paused=summary["paused"],
        actions=summary["actions"],
        warning=summary.get("warning"),
    )

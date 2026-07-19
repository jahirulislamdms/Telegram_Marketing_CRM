"""Contacts & CRM endpoints.

Managers/Admins manage all contacts; Agents see and act on their own assigned
contacts only. Import/resolve/bulk operations are Manager/Admin.
"""

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user, require_manager
from app.db.models.contact import Contact
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.contact import (
    BulkAssign,
    BulkConsent,
    BulkIds,
    BulkResolveResult,
    BulkStageUpdate,
    ContactCreate,
    ContactOut,
    ContactUpdate,
    ImportResult,
    MessageRequest,
    ResolveResult,
)
from app.services import accounts as account_service
from app.services import audit
from app.services import contacts as contact_service
from app.services import engine_client

router = APIRouter(prefix="/contacts", tags=["contacts"])


def _is_manager(user: User) -> bool:
    return user.role in ("admin", "manager")


async def _get_contact_or_404(db: AsyncSession, contact_id: int) -> Contact:
    contact = await contact_service.get_by_id(db, contact_id)
    if contact is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Contact not found")
    return contact


def _ensure_can_edit(user: User, contact: Contact) -> None:
    if _is_manager(user):
        return
    if contact.assigned_agent_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only act on contacts assigned to you",
        )


# ------------------------------------------------------- import / template ---


@router.get("/import-template")
async def import_template(_: User = Depends(require_manager)) -> Response:
    return Response(
        content=contact_service.CSV_TEMPLATE,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=contacts_template.csv"},
    )


@router.post("/import", response_model=ImportResult)
async def import_contacts(
    file: UploadFile = File(...),
    user: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> ImportResult:
    data = await file.read()
    try:
        rows = contact_service.parse_upload(file.filename or "", data)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not parse file: {exc}",
        )
    result = await contact_service.import_contacts(db, rows)
    await audit.record_event(
        db,
        type="contact.import",
        actor_type="user",
        actor_id=user.id,
        meta={k: result[k] for k in ("imported", "updated", "rejected_no_consent", "errors")},
    )
    return ImportResult(**result)


# --------------------------------------------------------------------- export ---


@router.get("/export")
async def export_contacts(
    format: str = Query(default="csv", pattern="^(csv|xlsx)$"),
    ids: str | None = Query(default=None, description="comma-separated ids to export"),
    stage: str | None = Query(default=None),
    source: str | None = Query(default=None),
    resolution: str | None = Query(default=None),
    lead_type: str | None = Query(default=None),
    consent: bool | None = Query(default=None),
    q: str | None = Query(default=None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    agent_filter = None if _is_manager(user) else user.id
    if ids:
        wanted = [int(x) for x in ids.split(",") if x.strip().lstrip("-").isdigit()]
        contacts = []
        for cid in wanted:
            contact = await contact_service.get_by_id(db, cid)
            if contact is None:
                continue
            if agent_filter is not None and contact.assigned_agent_id != agent_filter:
                continue
            contacts.append(contact)
    else:
        contacts = await contact_service.list_contacts(
            db,
            assigned_agent_id=agent_filter,
            stage=stage,
            source=source,
            resolution=resolution,
            lead_type=lead_type,
            consent=consent,
            q=q,
        )
    if format == "xlsx":
        body = contact_service.contacts_to_xlsx(contacts)
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = "contacts.xlsx"
    else:
        body = contact_service.contacts_to_csv(contacts)
        media = "text/csv"
        filename = "contacts.csv"
    return Response(
        content=body,
        media_type=media,
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ------------------------------------------------------------ bulk actions ---


@router.post("/resolve", response_model=BulkResolveResult)
async def bulk_resolve(
    payload: BulkIds,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> BulkResolveResult:
    resolved = no_tg = failed = 0
    for contact_id in payload.contact_ids:
        contact = await contact_service.get_by_id(db, contact_id)
        if contact is None:
            failed += 1
            continue
        try:
            updated = await contact_service.resolve_contact(db, contact)
        except (contact_service.NoResolverAccount, engine_client.EngineUnavailable):
            failed += 1
            continue
        if updated.resolution_status == "resolved":
            resolved += 1
        elif updated.resolution_status == "no_telegram":
            no_tg += 1
        else:
            failed += 1
    return BulkResolveResult(resolved=resolved, no_telegram=no_tg, failed=failed)


@router.post("/bulk/unresolve", response_model=int)
async def bulk_unresolve(
    payload: BulkIds,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> int:
    return await contact_service.bulk_unresolve(db, payload.contact_ids)


@router.post("/bulk/consent", response_model=int)
async def bulk_consent(
    payload: BulkConsent,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> int:
    return await contact_service.bulk_set_consent(db, payload.contact_ids, payload.consent)


@router.post("/bulk/stage", response_model=int)
async def bulk_stage(
    payload: BulkStageUpdate,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> int:
    count = 0
    for contact_id in payload.contact_ids:
        contact = await contact_service.get_by_id(db, contact_id)
        if contact is None:
            continue
        await contact_service.update_contact(
            db, contact, stage=payload.stage.value, opted_out=payload.stage.value == "opted_out" or None
        )
        count += 1
    return count


@router.post("/bulk/assign", response_model=int)
async def bulk_assign(
    payload: BulkAssign,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> int:
    count = 0
    for contact_id in payload.contact_ids:
        contact = await contact_service.get_by_id(db, contact_id)
        if contact is None:
            continue
        contact.assigned_agent_id = payload.assigned_agent_id
        count += 1
    await db.commit()
    return count


@router.post("/bulk/delete", response_model=int)
async def bulk_delete(
    payload: BulkIds,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> int:
    count = 0
    for contact_id in payload.contact_ids:
        contact = await contact_service.get_by_id(db, contact_id)
        if contact is not None:
            await db.delete(contact)
            count += 1
    await db.commit()
    return count


# -------------------------------------------------------------------- CRUD ---


@router.get("", response_model=list[ContactOut])
async def list_contacts(
    response: Response,
    stage: str | None = Query(default=None),
    source: str | None = Query(default=None),
    resolution: str | None = Query(default=None),
    lead_type: str | None = Query(default=None),
    consent: bool | None = Query(default=None),
    q: str | None = Query(default=None),
    in_destination: int | None = Query(default=None),
    not_in_destination: int | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=1000),
    offset: int | None = Query(default=None, ge=0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list:
    agent_filter = None if _is_manager(user) else user.id
    filters = dict(
        assigned_agent_id=agent_filter,
        stage=stage,
        source=source,
        resolution=resolution,
        lead_type=lead_type,
        consent=consent,
        q=q,
        in_destination=in_destination,
        not_in_destination=not_in_destination,
    )
    # Expose the unpaginated total so the UI can render "Showing X–Y of N".
    total = await contact_service.count_contacts(db, **filters)
    response.headers["X-Total-Count"] = str(total)
    response.headers["Access-Control-Expose-Headers"] = "X-Total-Count"
    return await contact_service.list_contacts(db, limit=limit, offset=offset, **filters)


@router.post("", response_model=ContactOut, status_code=status.HTTP_201_CREATED)
async def create_contact(
    payload: ContactCreate,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> ContactOut:
    try:
        return await contact_service.create_contact(
            db,
            name=payload.name,
            phone=payload.phone,
            username=payload.username,
            source=payload.source,
            notes=payload.notes,
            consent=payload.consent,
            tags=payload.tags,
        )
    except contact_service.DuplicateContact as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)


@router.get("/{contact_id}", response_model=ContactOut)
async def get_contact(
    contact_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactOut:
    contact = await _get_contact_or_404(db, contact_id)
    _ensure_can_edit(user, contact)
    return contact


@router.patch("/{contact_id}", response_model=ContactOut)
async def update_contact(
    contact_id: int,
    payload: ContactUpdate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactOut:
    contact = await _get_contact_or_404(db, contact_id)
    _ensure_can_edit(user, contact)
    # Agents may not reassign a contact to someone else.
    if not _is_manager(user) and payload.assigned_agent_id is not None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot reassign")

    fields = payload.model_dump(exclude_unset=True)
    if fields.get("stage") is not None:
        fields["stage"] = payload.stage.value
        if payload.stage.value == "opted_out":
            fields["opted_out"] = True

    # Identity fields go through edit_contact (normalise + uniqueness + lead_type);
    # the rest (stage/consent/assignment/tags) via the generic setter, unchanged.
    edit_keys = ("name", "phone", "username", "source", "notes")
    edit_updates = {k: fields.pop(k) for k in edit_keys if k in fields}
    if edit_updates:
        try:
            await contact_service.edit_contact(db, contact, edit_updates)
        except contact_service.DuplicateContact as exc:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=exc.message)
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    if fields:
        await contact_service.update_contact(db, contact, **fields)
    await db.refresh(contact)
    return contact


@router.delete("/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> None:
    contact = await _get_contact_or_404(db, contact_id)
    await contact_service.delete_contact(db, contact)


# ------------------------------------------------- resolve & message (one) ---


@router.post("/{contact_id}/resolve", response_model=ResolveResult)
async def resolve_one(
    contact_id: int,
    _: User = Depends(require_manager),
    db: AsyncSession = Depends(get_db),
) -> ResolveResult:
    contact = await _get_contact_or_404(db, contact_id)
    try:
        updated = await contact_service.resolve_contact(db, contact)
    except contact_service.NoResolverAccount:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No logged-in account available to resolve contacts",
        )
    except engine_client.EngineUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    return ResolveResult(
        id=updated.id,
        resolution_status=updated.resolution_status,
        telegram_user_id=updated.telegram_user_id,
    )


@router.post("/{contact_id}/message", response_model=ContactOut)
async def message_contact(
    contact_id: int,
    payload: MessageRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ContactOut:
    contact = await _get_contact_or_404(db, contact_id)
    _ensure_can_edit(user, contact)

    # Consent guardrail: only consented, non-opted-out contacts may be messaged.
    if not contact.consent or contact.opted_out:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Contact has not consented or has opted out",
        )

    account = await account_service.get_by_id(db, payload.account_id)
    if account is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Account not found")
    if not account.session_ref:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Chosen account is not logged in"
        )

    try:
        updated = await contact_service.message_contact(db, contact, account, payload.text)
    except engine_client.EngineUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
    await audit.record_event(
        db,
        type="contact.message",
        actor_type="user",
        actor_id=user.id,
        entity_ref=f"contact:{contact.id}",
        meta={"account_id": account.id},
    )
    return updated

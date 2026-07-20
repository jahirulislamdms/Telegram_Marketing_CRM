"""Staff management endpoints (Admin only)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_admin
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.user import UserCreate, UserOut, UserUpdate
from app.services import audit
from app.services import users as user_service

router = APIRouter(prefix="/users", tags=["staff"])


@router.get("", response_model=list[UserOut])
async def list_staff(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    return await user_service.list_users(db)


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
async def create_staff(
    payload: UserCreate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    if await user_service.get_by_email(db, payload.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )
    user = await user_service.create_user(
        db,
        email=payload.email,
        password=payload.password,
        full_name=payload.full_name,
        role=payload.role.value,
    )
    await audit.record_event(
        db,
        type="user.create",
        actor_type="user",
        actor_id=admin.id,
        entity_ref=f"user:{user.id}",
        meta={"email": user.email, "role": user.role},
    )
    return user


@router.get("/{user_id}", response_model=UserOut)
async def get_staff(
    user_id: int,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await user_service.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return user


@router.patch("/{user_id}", response_model=UserOut)
async def update_staff(
    user_id: int,
    payload: UserUpdate,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    user = await user_service.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id and payload.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account",
        )
    fields = payload.model_dump(exclude_unset=True)
    if "full_name" in fields and not (fields.get("full_name") or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Name is required.",
        )
    if payload.email is not None and await user_service.email_taken(
        db, str(payload.email), exclude_id=user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email address is already in use.",
        )
    updated = await user_service.update_user(
        db,
        user,
        full_name=payload.full_name,
        email=str(payload.email) if payload.email is not None else None,
        role=payload.role.value if payload.role is not None else None,
        is_active=payload.is_active,
        password=payload.password,
    )
    await audit.record_event(
        db,
        type="user.update",
        actor_type="user",
        actor_id=admin.id,
        entity_ref=f"user:{updated.id}",
    )
    return updated


@router.delete("/{user_id}", response_model=UserOut)
async def deactivate_staff(
    user_id: int,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Soft-delete: deactivate the account (data is retained for audit)."""
    user = await user_service.get_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account",
        )
    updated = await user_service.update_user(db, user, is_active=False)
    await audit.record_event(
        db,
        type="user.deactivate",
        actor_type="user",
        actor_id=admin.id,
        entity_ref=f"user:{updated.id}",
    )
    return updated

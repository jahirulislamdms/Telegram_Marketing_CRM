"""Authentication endpoints: login, token refresh, and self-profile."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.auth.security import (
    REFRESH_TOKEN_TYPE,
    JWTError,
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.auth import AccessToken, LoginRequest, RefreshRequest, TokenPair
from app.schemas.user import MeUpdate, PasswordChange, UserOut
from app.services import audit
from app.services import auth as auth_service
from app.services import users as user_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenPair)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenPair:
    user = await auth_service.authenticate(db, payload.email, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    await auth_service.mark_logged_in(db, user)
    await audit.record_event(
        db,
        type="user.login",
        actor_type="user",
        actor_id=user.id,
        entity_ref=f"user:{user.id}",
    )
    return TokenPair(
        access_token=create_access_token(user.id),
        refresh_token=create_refresh_token(user.id),
    )


@router.post("/refresh", response_model=AccessToken)
async def refresh(
    payload: RefreshRequest, db: AsyncSession = Depends(get_db)
) -> AccessToken:
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token"
    )
    try:
        claims = decode_token(payload.refresh_token)
        if claims.get("type") != REFRESH_TOKEN_TYPE:
            raise invalid
        user_id = int(claims["sub"])
    except (JWTError, KeyError, ValueError, TypeError):
        raise invalid

    user = await user_service.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise invalid
    return AccessToken(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
async def me(current: User = Depends(get_current_user)) -> User:
    return current


@router.patch("/me", response_model=UserOut)
async def update_me(
    payload: MeUpdate,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    fields = payload.model_dump(exclude_unset=True)
    # Name, if being set, cannot be blank (§15.4 #3 validation).
    if "full_name" in fields and not (fields.get("full_name") or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Name cannot be empty.",
        )
    # Email must stay unique.
    if payload.email is not None and await user_service.email_taken(
        db, str(payload.email), exclude_id=current.id
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This email address is already in use.",
        )
    updated = await user_service.update_user(
        db,
        current,
        full_name=payload.full_name,
        email=str(payload.email) if payload.email is not None else None,
        theme=payload.theme.value if payload.theme is not None else None,
        password=payload.password,
    )
    return updated


@router.post("/change-password", status_code=status.HTTP_200_OK)
async def change_password(
    payload: PasswordChange,
    current: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Self-service password change. The current password is verified; existing
    tokens stay valid so the user is NOT logged out (§15.4 #4)."""
    if not verify_password(payload.current_password, current.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect.",
        )
    await user_service.update_user(db, current, password=payload.new_password)
    await audit.record_event(
        db,
        type="user.password_change",
        actor_type="user",
        actor_id=current.id,
        entity_ref=f"user:{current.id}",
    )
    return {"detail": "Password changed successfully."}

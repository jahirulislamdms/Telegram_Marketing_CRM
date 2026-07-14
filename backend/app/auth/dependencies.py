"""FastAPI auth dependencies: current-user resolution and RBAC guards."""

from collections.abc import Callable, Coroutine
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import ACCESS_TOKEN_TYPE, JWTError, decode_token
from app.db.models.constants import UserRole
from app.db.models.user import User
from app.db.session import get_db
from app.services import users as user_service

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=True)

_credentials_exc = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Could not validate credentials",
    headers={"WWW-Authenticate": "Bearer"},
)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    try:
        payload = decode_token(token)
        if payload.get("type") != ACCESS_TOKEN_TYPE:
            raise _credentials_exc
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError, TypeError):
        raise _credentials_exc

    user = await user_service.get_by_id(db, user_id)
    if user is None or not user.is_active:
        raise _credentials_exc
    return user


def require_roles(
    *roles: UserRole,
) -> Callable[..., Coroutine[Any, Any, User]]:
    """Dependency factory enforcing that the current user has one of ``roles``."""
    allowed = {r.value for r in roles}

    async def _guard(current: User = Depends(get_current_user)) -> User:
        if current.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this action",
            )
        return current

    return _guard


# Common guards.
require_admin = require_roles(UserRole.admin)
require_manager = require_roles(UserRole.admin, UserRole.manager)

"""Authentication service."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import verify_password
from app.db.models.user import User
from app.services import users as user_service


async def authenticate(db: AsyncSession, email: str, password: str) -> User | None:
    """Return the user if credentials are valid and the account is active."""
    user = await user_service.get_by_email(db, email)
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def mark_logged_in(db: AsyncSession, user: User) -> None:
    user.last_login = datetime.now(timezone.utc)
    await db.commit()

"""User (staff) persistence and business logic."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password
from app.db.models.constants import UserRole
from app.db.models.user import User


async def get_by_id(db: AsyncSession, user_id: int) -> User | None:
    return await db.get(User, user_id)


async def get_by_email(db: AsyncSession, email: str) -> User | None:
    result = await db.execute(select(User).where(User.email == email.lower()))
    return result.scalar_one_or_none()


async def list_users(db: AsyncSession) -> list[User]:
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    return list(result.scalars().all())


async def count_users(db: AsyncSession) -> int:
    result = await db.execute(select(func.count()).select_from(User))
    return int(result.scalar_one())


async def create_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str | None,
    role: str = UserRole.agent.value,
) -> User:
    user = User(
        email=email.lower(),
        password_hash=hash_password(password),
        full_name=full_name,
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def update_user(
    db: AsyncSession,
    user: User,
    *,
    full_name: str | None = None,
    role: str | None = None,
    theme: str | None = None,
    is_active: bool | None = None,
    password: str | None = None,
) -> User:
    if full_name is not None:
        user.full_name = full_name
    if role is not None:
        user.role = role
    if theme is not None:
        user.theme = theme
    if is_active is not None:
        user.is_active = is_active
    if password:
        user.password_hash = hash_password(password)
    await db.commit()
    await db.refresh(user)
    return user

"""User (staff) schemas."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.db.models.constants import Theme, UserRole


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str | None
    role: UserRole
    theme: Theme
    is_active: bool
    created_at: datetime
    last_login: datetime | None


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str | None = Field(default=None, max_length=255)
    role: UserRole = UserRole.agent


class UserUpdate(BaseModel):
    """Admin-side update of another user."""

    full_name: str | None = Field(default=None, max_length=255)
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)


class MeUpdate(BaseModel):
    """Self-service update of the current user's own profile."""

    full_name: str | None = Field(default=None, max_length=255)
    theme: Theme | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)

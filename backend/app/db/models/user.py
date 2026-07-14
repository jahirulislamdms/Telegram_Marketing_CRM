"""Staff user model."""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.constants import Theme, UserRole


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint(
            "role in ('admin','manager','agent')", name="role_valid"
        ),
        CheckConstraint("theme in ('dark','light')", name="theme_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(
        String(255), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(
        String(20), nullable=False, default=UserRole.agent.value
    )
    theme: Mapped[str] = mapped_column(
        String(10), nullable=False, default=Theme.dark.value
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=func.true()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<User id={self.id} email={self.email!r} role={self.role}>"

"""Telegram account (userbot) model."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# active / warming / quarantined / banned / logged_out
ACCOUNT_STATUSES = ("active", "warming", "quarantined", "banned", "logged_out")


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (
        CheckConstraint(
            "status in ('active','warming','quarantined','banned','logged_out')",
            name="account_status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # Per-account API creds are optional; blank means "use the shared API ID/HASH".
    api_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    api_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Reference to the persisted Telethon session (the engine maps this to a file
    # under sessions/). Null until the account has logged in.
    session_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    proxy_id: Mapped[int | None] = mapped_column(
        ForeignKey("proxies.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="logged_out", server_default="logged_out"
    )
    warmup_stage: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    warmup_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    daily_cap: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30, server_default="30"
    )
    actions_today: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_action_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    spam_state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="unknown", server_default="unknown"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Account id={self.id} label={self.label!r} status={self.status}>"

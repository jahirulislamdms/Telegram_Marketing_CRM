"""Proxy pool model.

Proxies are pasted in bulk in Settings; the engine auto-assigns one free, healthy
proxy from the pool to each account (one proxy per account).
"""

from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Proxy(Base):
    __tablename__ = "proxies"
    __table_args__ = (
        CheckConstraint(
            "type in ('socks5','http','mtproxy')", name="proxy_type_valid"
        ),
        CheckConstraint("health in ('ok','dead','unknown')", name="proxy_health_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    raw: Mapped[str] = mapped_column(String(500), nullable=False)
    type: Mapped[str] = mapped_column(String(10), nullable=False, default="socks5")
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=func.true()
    )
    # Back-reference (no FK, to avoid a circular dependency with accounts.proxy_id).
    assigned_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    health: Mapped[str] = mapped_column(String(10), nullable=False, default="unknown")
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Proxy id={self.id} {self.type}://{self.host}:{self.port} health={self.health}>"

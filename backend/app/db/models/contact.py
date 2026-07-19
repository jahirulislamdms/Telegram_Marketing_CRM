"""Contact (lead) model."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.types import JSONType


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        CheckConstraint(
            "lead_type in ('phone','username')", name="contact_lead_type_valid"
        ),
        CheckConstraint(
            "resolution_status in ('pending','resolved','no_telegram','failed')",
            name="contact_resolution_valid",
        ),
        CheckConstraint(
            "stage in ('new','contacted','replied','joined','customer','opted_out')",
            name="contact_stage_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Name is optional; the display label falls back to username, then phone.
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lead_type: Mapped[str] = mapped_column(String(20), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    # Stored lowercased, without a leading '@'.
    username: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    telegram_user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    resolution_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # Free-form CRM notes (§15.3); optional, unbounded.
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    stage: Mapped[str] = mapped_column(
        String(20), nullable=False, default="new", server_default="new"
    )
    consent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    opted_out: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    assigned_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    assigned_agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    utm: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    tags: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_contacted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    @property
    def display_label(self) -> str:
        if self.name:
            return self.name
        if self.username:
            return f"@{self.username}"
        if self.phone:
            return self.phone
        return f"#{self.id}"

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Contact id={self.id} {self.display_label!r} stage={self.stage}>"

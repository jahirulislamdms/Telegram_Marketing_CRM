"""Templates, campaigns, and campaign targets."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.types import JSONType


class Template(Base):
    __tablename__ = "templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    include_link: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    link_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    media_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Templates sharing a variant_group are A/B variants of each other.
    variant_group: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    variant_label: Mapped[str] = mapped_column(
        String(10), nullable=False, default="A", server_default="A"
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        CheckConstraint(
            "action in ('message','invite','add')", name="campaign_action_valid"
        ),
        CheckConstraint(
            "status in ('draft','running','paused','done')", name="campaign_status_valid"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(
        String(20), nullable=False, default="message", server_default="message"
    )
    destination_id: Mapped[int | None] = mapped_column(
        ForeignKey("destinations.id", ondelete="SET NULL"), nullable=True
    )
    # Segment filter, e.g. {source, stage, tag, exclude_in_destination}.
    segment: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    # Drip steps: list of {offset_hours, variant_group}.
    steps: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    ab_test: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft"
    )
    last_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class CampaignTarget(Base):
    __tablename__ = "campaign_targets"
    __table_args__ = (
        UniqueConstraint("campaign_id", "contact_id", "step", name="uq_campaign_target"),
        CheckConstraint(
            "result in ('queued','sent','replied','joined','failed','skipped')",
            name="campaign_target_result_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False, index=True
    )
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("templates.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    scheduled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result: Mapped[str] = mapped_column(
        String(20), nullable=False, default="queued", server_default="queued"
    )
    error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

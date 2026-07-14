"""Warmup models: runs, participants (fleet accounts), and external partners."""

from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.db.models.types import JSONType


class WarmupRun(Base):
    __tablename__ = "warmup_runs"
    __table_args__ = (
        CheckConstraint(
            "status in ('draft','running','paused','done')", name="warmup_status_valid"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="draft", server_default="draft"
    )
    # Staged ramp: list of {days, max_actions}.
    stages: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    # Group/channel links to join and casual chit-chat lines.
    groups: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    messages: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    min_delay_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=40, server_default="40"
    )
    max_delay_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=180, server_default="180"
    )
    created_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WarmupParticipant(Base):
    __tablename__ = "warmup_participants"
    __table_args__ = (
        UniqueConstraint("run_id", "account_id", name="uq_warmup_participant"),
        CheckConstraint(
            "status in ('pending','active','paused','done')",
            name="warmup_participant_status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("warmup_runs.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    stage: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    stage_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actions_today: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    day_key: Mapped[str | None] = mapped_column(String(10), nullable=True)
    last_action_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    joined: Mapped[list] = mapped_column(JSONType, nullable=False, default=list)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="pending", server_default="pending"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class WarmupPartner(Base):
    __tablename__ = "warmup_partners"
    __table_args__ = (
        CheckConstraint("kind in ('phone','username')", name="warmup_partner_kind_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("warmup_runs.id", ondelete="CASCADE"), nullable=False
    )
    identifier: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

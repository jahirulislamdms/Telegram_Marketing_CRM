"""Referral model — personal invite codes + reward tracking for subscribers.

A subscriber gets a personal ``invite_code`` (surfaced as a bot deep-link
``?start=ref_<code>``). When a new subscriber starts the bot with that payload,
the matching referral's ``invited_count`` is incremented. ``rewarded`` marks that
the reward for those invites has been granted.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Referral(Base):
    __tablename__ = "referrals"

    id: Mapped[int] = mapped_column(primary_key=True)
    referrer_subscriber_id: Mapped[int] = mapped_column(
        ForeignKey("bot_subscribers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    invite_code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    invited_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    rewarded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=func.false()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Referral id={self.id} code={self.invite_code!r} "
            f"invited={self.invited_count} rewarded={self.rewarded}>"
        )

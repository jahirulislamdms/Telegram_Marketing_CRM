"""Event model — analytics + audit log.

Records staff actions (login, user create/update/deactivate, ...) and, in later
phases, account/system events. ``actor_type`` is one of user/account/system.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

# JSONB on PostgreSQL, portable JSON elsewhere (e.g. SQLite in tests).
JSONType = JSON().with_variant(JSONB, "postgresql")


class Event(Base):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(primary_key=True)
    type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="system"
    )
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    entity_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    meta: Mapped[dict] = mapped_column(JSONType, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), index=True
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Event id={self.id} type={self.type!r} actor={self.actor_type}:{self.actor_id}>"

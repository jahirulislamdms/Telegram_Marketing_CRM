"""Inbox models: conversations and messages."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
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


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        UniqueConstraint("account_id", "peer_id", name="uq_conversation_account_peer"),
        CheckConstraint(
            "status in ('new','contacted','replied','joined','customer','opted_out','blocked')",
            name="conversation_status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    account_id: Mapped[int] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), nullable=False
    )
    # Telegram identity of the other party (for conversations without a contact row).
    peer_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    peer_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_message_preview: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unread_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="new", server_default="new"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("direction in ('in','out')", name="message_direction_valid"),
        CheckConstraint(
            "type in ('text','image','voice','link','video','gif','sticker','audio','file')",
            name="message_type_valid",
        ),
        CheckConstraint(
            "status in ('queued','sent','delivered','failed','read')",
            name="message_status_valid",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    account_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), nullable=True
    )
    sender: Mapped[str] = mapped_column(String(40), nullable=False, default="system")
    type: Mapped[str] = mapped_column(String(10), nullable=False, default="text")
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tg_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="sent", server_default="sent"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

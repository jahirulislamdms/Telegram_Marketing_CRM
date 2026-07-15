"""Bot models: bots, subscribers, conversations, messages."""

from datetime import datetime

from sqlalchemy import (
    BigInteger,
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


class Bot(Base):
    __tablename__ = "bots"
    __table_args__ = (
        CheckConstraint("mode in ('polling','webhook')", name="bot_mode_valid"),
        CheckConstraint("status in ('running','stopped','error')", name="bot_status_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    username: Mapped[str | None] = mapped_column(String(120), nullable=True)
    token: Mapped[str] = mapped_column(String(255), nullable=False)
    mode: Mapped[str] = mapped_column(
        String(20), nullable=False, default="polling", server_default="polling"
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="stopped", server_default="stopped"
    )
    webhook_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    started_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    active_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BotSubscriber(Base):
    __tablename__ = "bot_subscribers"
    __table_args__ = (
        UniqueConstraint("bot_id", "telegram_user_id", name="uq_bot_subscriber"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(
        ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    telegram_user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id", ondelete="SET NULL"), nullable=True
    )
    utm_source: Mapped[str | None] = mapped_column(String(120), nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_active_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=func.true()
    )
    is_subscribed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=func.true()
    )


class BotConversation(Base):
    __tablename__ = "bot_conversations"
    __table_args__ = (
        UniqueConstraint("bot_id", "subscriber_id", name="uq_bot_conversation"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_id: Mapped[int] = mapped_column(
        ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True
    )
    subscriber_id: Mapped[int] = mapped_column(
        ForeignKey("bot_subscribers.id", ondelete="CASCADE"), nullable=False
    )
    last_message_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_message_preview: Mapped[str | None] = mapped_column(String(255), nullable=True)
    unread_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    assigned_agent_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="open", server_default="open"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class BotMessage(Base):
    __tablename__ = "bot_messages"
    __table_args__ = (
        CheckConstraint("direction in ('in','out')", name="bot_message_direction_valid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    bot_conversation_id: Mapped[int] = mapped_column(
        ForeignKey("bot_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    direction: Mapped[str] = mapped_column(String(3), nullable=False)
    sender: Mapped[str] = mapped_column(String(40), nullable=False, default="subscriber")
    type: Mapped[str] = mapped_column(String(10), nullable=False, default="text")
    body: Mapped[str | None] = mapped_column(Text, nullable=True)
    media_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tg_message_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

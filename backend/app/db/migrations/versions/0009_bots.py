"""bots, subscribers, conversations, messages

Revision ID: 0009_bots
Revises: 0008_campaigns
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0009_bots"
down_revision: Union[str, None] = "0008_campaigns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "bots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=True),
        sa.Column("username", sa.String(length=120), nullable=True),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("mode", sa.String(length=20), nullable=False, server_default="polling"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="stopped"),
        sa.Column("webhook_url", sa.String(length=500), nullable=True),
        sa.Column("started_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("active_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("mode in ('polling','webhook')", name="ck_bots_bot_mode_valid"),
        sa.CheckConstraint("status in ('running','stopped','error')", name="ck_bots_bot_status_valid"),
        sa.PrimaryKeyConstraint("id", name="pk_bots"),
    )
    op.create_table(
        "bot_subscribers",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bot_id", sa.Integer(), nullable=False),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("contact_id", sa.Integer(), nullable=True),
        sa.Column("utm_source", sa.String(length=120), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_active_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("is_subscribed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.ForeignKeyConstraint(["bot_id"], ["bots.id"], name="fk_bot_subscribers_bot_id_bots", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["contact_id"], ["contacts.id"], name="fk_bot_subscribers_contact_id_contacts", ondelete="SET NULL"),
        sa.UniqueConstraint("bot_id", "telegram_user_id", name="uq_bot_subscriber"),
        sa.PrimaryKeyConstraint("id", name="pk_bot_subscribers"),
    )
    op.create_index("ix_bot_subscribers_bot_id", "bot_subscribers", ["bot_id"])
    op.create_table(
        "bot_conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bot_id", sa.Integer(), nullable=False),
        sa.Column("subscriber_id", sa.Integer(), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_preview", sa.String(length=255), nullable=True),
        sa.Column("unread_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("assigned_agent_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="open"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["bot_id"], ["bots.id"], name="fk_bot_conversations_bot_id_bots", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subscriber_id"], ["bot_subscribers.id"], name="fk_bot_conversations_subscriber_id_bot_subscribers", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_agent_id"], ["users.id"], name="fk_bot_conversations_assigned_agent_id_users", ondelete="SET NULL"),
        sa.UniqueConstraint("bot_id", "subscriber_id", name="uq_bot_conversation"),
        sa.PrimaryKeyConstraint("id", name="pk_bot_conversations"),
    )
    op.create_index("ix_bot_conversations_bot_id", "bot_conversations", ["bot_id"])
    op.create_table(
        "bot_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bot_conversation_id", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=3), nullable=False),
        sa.Column("sender", sa.String(length=40), nullable=False),
        sa.Column("type", sa.String(length=10), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("media_ref", sa.String(length=500), nullable=True),
        sa.Column("tg_message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("direction in ('in','out')", name="ck_bot_messages_bot_message_direction_valid"),
        sa.ForeignKeyConstraint(["bot_conversation_id"], ["bot_conversations.id"], name="fk_bot_messages_bot_conversation_id_bot_conversations", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_bot_messages"),
    )
    op.create_index("ix_bot_messages_bot_conversation_id", "bot_messages", ["bot_conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_bot_messages_bot_conversation_id", table_name="bot_messages")
    op.drop_table("bot_messages")
    op.drop_index("ix_bot_conversations_bot_id", table_name="bot_conversations")
    op.drop_table("bot_conversations")
    op.drop_index("ix_bot_subscribers_bot_id", table_name="bot_subscribers")
    op.drop_table("bot_subscribers")
    op.drop_table("bots")

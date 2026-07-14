"""conversations and messages tables

Revision ID: 0005_inbox
Revises: 0004_contacts
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0005_inbox"
down_revision: Union[str, None] = "0004_contacts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=True),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("peer_id", sa.BigInteger(), nullable=True),
        sa.Column("peer_name", sa.String(length=255), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_preview", sa.String(length=255), nullable=True),
        sa.Column("unread_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="new"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status in ('new','contacted','replied','joined','customer','opted_out','blocked')",
            name="ck_conversations_conversation_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"], ["contacts.id"],
            name="fk_conversations_contact_id_contacts", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"],
            name="fk_conversations_account_id_accounts", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("account_id", "peer_id", name="uq_conversation_account_peer"),
        sa.PrimaryKeyConstraint("id", name="pk_conversations"),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("conversation_id", sa.Integer(), nullable=False),
        sa.Column("direction", sa.String(length=3), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("sender", sa.String(length=40), nullable=False),
        sa.Column("type", sa.String(length=10), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("media_ref", sa.String(length=500), nullable=True),
        sa.Column("tg_message_id", sa.BigInteger(), nullable=True),
        sa.Column("status", sa.String(length=10), nullable=False, server_default="sent"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "direction in ('in','out')", name="ck_messages_message_direction_valid"
        ),
        sa.CheckConstraint(
            "type in ('text','image','voice','link')", name="ck_messages_message_type_valid"
        ),
        sa.CheckConstraint(
            "status in ('queued','sent','delivered','failed','read')",
            name="ck_messages_message_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"],
            name="fk_messages_conversation_id_conversations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"],
            name="fk_messages_account_id_accounts", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_messages"),
    )
    op.create_index("ix_messages_conversation_id", "messages", ["conversation_id"])


def downgrade() -> None:
    op.drop_index("ix_messages_conversation_id", table_name="messages")
    op.drop_table("messages")
    op.drop_table("conversations")

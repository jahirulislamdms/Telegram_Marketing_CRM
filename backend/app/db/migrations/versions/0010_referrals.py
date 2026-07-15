"""referrals

Revision ID: 0010_referrals
Revises: 0009_bots
Create Date: 2026-07-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_referrals"
down_revision: Union[str, None] = "0009_bots"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "referrals",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("referrer_subscriber_id", sa.Integer(), nullable=False),
        sa.Column("invite_code", sa.String(length=64), nullable=False),
        sa.Column("invited_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("rewarded", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["referrer_subscriber_id"], ["bot_subscribers.id"],
            name="fk_referrals_referrer_subscriber_id_bot_subscribers", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("invite_code", name="uq_referrals_invite_code"),
        sa.PrimaryKeyConstraint("id", name="pk_referrals"),
    )
    op.create_index("ix_referrals_referrer_subscriber_id", "referrals", ["referrer_subscriber_id"])


def downgrade() -> None:
    op.drop_index("ix_referrals_referrer_subscriber_id", table_name="referrals")
    op.drop_table("referrals")

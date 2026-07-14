"""accounts and proxies tables

Revision ID: 0002_accounts_proxies
Revises: 0001_users_events
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0002_accounts_proxies"
down_revision: Union[str, None] = "0001_users_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "proxies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("raw", sa.String(length=500), nullable=False),
        sa.Column("type", sa.String(length=10), nullable=False, server_default="socks5"),
        sa.Column("host", sa.String(length=255), nullable=False),
        sa.Column("port", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("password", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("assigned_account_id", sa.Integer(), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("health", sa.String(length=10), nullable=False, server_default="unknown"),
        sa.Column("notes", sa.String(length=500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "type in ('socks5','http','mtproxy')", name="ck_proxies_proxy_type_valid"
        ),
        sa.CheckConstraint(
            "health in ('ok','dead','unknown')", name="ck_proxies_proxy_health_valid"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_proxies"),
    )

    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=120), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("api_id", sa.String(length=32), nullable=True),
        sa.Column("api_hash", sa.String(length=64), nullable=True),
        sa.Column("session_ref", sa.String(length=255), nullable=True),
        sa.Column("proxy_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="logged_out"),
        sa.Column("warmup_stage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warmup_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("daily_cap", sa.Integer(), nullable=False, server_default="30"),
        sa.Column("actions_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_action_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("spam_state", sa.String(length=20), nullable=False, server_default="unknown"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status in ('active','warming','quarantined','banned','logged_out')",
            name="ck_accounts_account_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["proxy_id"],
            ["proxies.id"],
            name="fk_accounts_proxy_id_proxies",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_accounts"),
    )


def downgrade() -> None:
    op.drop_table("accounts")
    op.drop_table("proxies")

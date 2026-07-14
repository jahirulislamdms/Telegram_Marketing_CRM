"""warmup runs, participants, and partners

Revision ID: 0003_warmup
Revises: 0002_accounts_proxies
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0003_warmup"
down_revision: Union[str, None] = "0002_accounts_proxies"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    op.create_table(
        "warmup_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("stages", JSONType, nullable=False),
        sa.Column("groups", JSONType, nullable=False),
        sa.Column("messages", JSONType, nullable=False),
        sa.Column("min_delay_seconds", sa.Integer(), nullable=False, server_default="40"),
        sa.Column("max_delay_seconds", sa.Integer(), nullable=False, server_default="180"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status in ('draft','running','paused','done')",
            name="ck_warmup_runs_warmup_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_warmup_runs_created_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_warmup_runs"),
    )

    op.create_table(
        "warmup_participants",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("stage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actions_today", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("day_key", sa.String(length=10), nullable=True),
        sa.Column("last_action_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("joined", JSONType, nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status in ('pending','active','paused','done')",
            name="ck_warmup_participants_warmup_participant_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["warmup_runs.id"],
            name="fk_warmup_participants_run_id_warmup_runs", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"],
            name="fk_warmup_participants_account_id_accounts", ondelete="CASCADE",
        ),
        sa.UniqueConstraint("run_id", "account_id", name="uq_warmup_participant"),
        sa.PrimaryKeyConstraint("id", name="pk_warmup_participants"),
    )

    op.create_table(
        "warmup_partners",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("identifier", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "kind in ('phone','username')", name="ck_warmup_partners_warmup_partner_kind_valid"
        ),
        sa.ForeignKeyConstraint(
            ["run_id"], ["warmup_runs.id"],
            name="fk_warmup_partners_run_id_warmup_runs", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_warmup_partners"),
    )


def downgrade() -> None:
    op.drop_table("warmup_partners")
    op.drop_table("warmup_participants")
    op.drop_table("warmup_runs")

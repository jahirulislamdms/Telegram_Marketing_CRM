"""send jobs and targets

Revision ID: 0006_sender
Revises: 0005_inbox
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0006_sender"
down_revision: Union[str, None] = "0005_inbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "send_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("template", sa.Text(), nullable=False),
        sa.Column("include_link", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("link_url", sa.String(length=500), nullable=True),
        sa.Column(
            "suppress_link_first", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column("active_start", sa.String(length=5), nullable=False, server_default="00:00"),
        sa.Column("active_end", sa.String(length=5), nullable=False, server_default="23:59"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("last_account_id", sa.Integer(), nullable=True),
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
            name="ck_send_jobs_send_job_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_send_jobs_created_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_send_jobs"),
    )

    op.create_table(
        "send_targets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("rendered_body", sa.Text(), nullable=True),
        sa.Column("error", sa.String(length=255), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status in ('queued','sent','replied','failed','skipped')",
            name="ck_send_targets_send_target_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"], ["send_jobs.id"],
            name="fk_send_targets_job_id_send_jobs", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"], ["contacts.id"],
            name="fk_send_targets_contact_id_contacts", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"],
            name="fk_send_targets_account_id_accounts", ondelete="SET NULL",
        ),
        sa.UniqueConstraint("job_id", "contact_id", name="uq_send_target"),
        sa.PrimaryKeyConstraint("id", name="pk_send_targets"),
    )
    op.create_index("ix_send_targets_job_id", "send_targets", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_send_targets_job_id", table_name="send_targets")
    op.drop_table("send_targets")
    op.drop_table("send_jobs")

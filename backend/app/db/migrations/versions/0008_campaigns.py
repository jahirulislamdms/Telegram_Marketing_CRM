"""templates, campaigns, and campaign targets

Revision ID: 0008_campaigns
Revises: 0007_destinations
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0008_campaigns"
down_revision: Union[str, None] = "0007_destinations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    op.create_table(
        "templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("include_link", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("link_url", sa.String(length=500), nullable=True),
        sa.Column("media_ref", sa.String(length=500), nullable=True),
        sa.Column("variant_group", sa.String(length=60), nullable=False),
        sa.Column("variant_label", sa.String(length=10), nullable=False, server_default="A"),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_templates_created_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_templates"),
    )
    op.create_index("ix_templates_variant_group", "templates", ["variant_group"])

    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("action", sa.String(length=20), nullable=False, server_default="message"),
        sa.Column("destination_id", sa.Integer(), nullable=True),
        sa.Column("segment", JSONType, nullable=False),
        sa.Column("steps", JSONType, nullable=False),
        sa.Column("ab_test", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("last_account_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "action in ('message','invite','add')", name="ck_campaigns_campaign_action_valid"
        ),
        sa.CheckConstraint(
            "status in ('draft','running','paused','done')",
            name="ck_campaigns_campaign_status_valid",
        ),
        sa.ForeignKeyConstraint(
            ["destination_id"], ["destinations.id"],
            name="fk_campaigns_destination_id_destinations", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name="fk_campaigns_created_by_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_campaigns"),
    )

    op.create_table(
        "campaign_targets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("campaign_id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=False),
        sa.Column("step", sa.Integer(), nullable=False),
        sa.Column("template_id", sa.Integer(), nullable=True),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("error", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "result in ('queued','sent','replied','joined','failed','skipped')",
            name="ck_campaign_targets_campaign_target_result_valid",
        ),
        sa.ForeignKeyConstraint(
            ["campaign_id"], ["campaigns.id"],
            name="fk_campaign_targets_campaign_id_campaigns", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"], ["contacts.id"],
            name="fk_campaign_targets_contact_id_contacts", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"], ["templates.id"],
            name="fk_campaign_targets_template_id_templates", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"],
            name="fk_campaign_targets_account_id_accounts", ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "campaign_id", "contact_id", "step", name="uq_campaign_target"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_campaign_targets"),
    )
    op.create_index("ix_campaign_targets_campaign_id", "campaign_targets", ["campaign_id"])


def downgrade() -> None:
    op.drop_index("ix_campaign_targets_campaign_id", table_name="campaign_targets")
    op.drop_table("campaign_targets")
    op.drop_table("campaigns")
    op.drop_index("ix_templates_variant_group", table_name="templates")
    op.drop_table("templates")

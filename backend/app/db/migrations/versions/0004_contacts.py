"""contacts table

Revision ID: 0004_contacts
Revises: 0003_warmup
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0004_contacts"
down_revision: Union[str, None] = "0003_warmup"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

JSONType = sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("lead_type", sa.String(length=20), nullable=False),
        sa.Column("phone", sa.String(length=32), nullable=True),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True),
        sa.Column(
            "resolution_status", sa.String(length=20), nullable=False, server_default="pending"
        ),
        sa.Column("source", sa.String(length=120), nullable=True),
        sa.Column("stage", sa.String(length=20), nullable=False, server_default="new"),
        sa.Column("consent", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("opted_out", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("assigned_account_id", sa.Integer(), nullable=True),
        sa.Column("assigned_agent_id", sa.Integer(), nullable=True),
        sa.Column("utm", JSONType, nullable=False),
        sa.Column("tags", JSONType, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_contacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "lead_type in ('phone','username')", name="ck_contacts_contact_lead_type_valid"
        ),
        sa.CheckConstraint(
            "resolution_status in ('pending','resolved','no_telegram','failed')",
            name="ck_contacts_contact_resolution_valid",
        ),
        sa.CheckConstraint(
            "stage in ('new','contacted','replied','joined','customer','opted_out')",
            name="ck_contacts_contact_stage_valid",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_account_id"], ["accounts.id"],
            name="fk_contacts_assigned_account_id_accounts", ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_agent_id"], ["users.id"],
            name="fk_contacts_assigned_agent_id_users", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_contacts"),
    )
    op.create_index("ix_contacts_phone", "contacts", ["phone"])
    op.create_index("ix_contacts_username", "contacts", ["username"])


def downgrade() -> None:
    op.drop_index("ix_contacts_username", table_name="contacts")
    op.drop_index("ix_contacts_phone", table_name="contacts")
    op.drop_table("contacts")

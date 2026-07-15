"""destinations and group memberships

Revision ID: 0007_destinations
Revises: 0006_sender
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "0007_destinations"
down_revision: Union[str, None] = "0006_sender"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "destinations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("link", sa.String(length=500), nullable=False),
        sa.Column("tg_entity_id", sa.BigInteger(), nullable=True),
        sa.Column("type", sa.String(length=20), nullable=False, server_default="unknown"),
        sa.Column("invite_link", sa.String(length=500), nullable=True),
        sa.Column("added_via", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "type in ('group','channel','unknown')",
            name="ck_destinations_destination_type_valid",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_destinations"),
    )

    op.create_table(
        "group_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=False),
        sa.Column("destination_id", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("method", sa.String(length=20), nullable=True),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("error", sa.String(length=255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "state in ('pending','added','invited','joined','failed')",
            name="ck_group_memberships_group_membership_state_valid",
        ),
        sa.ForeignKeyConstraint(
            ["contact_id"], ["contacts.id"],
            name="fk_group_memberships_contact_id_contacts", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["destination_id"], ["destinations.id"],
            name="fk_group_memberships_destination_id_destinations", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["accounts.id"],
            name="fk_group_memberships_account_id_accounts", ondelete="SET NULL",
        ),
        sa.UniqueConstraint("contact_id", "destination_id", name="uq_group_membership"),
        sa.PrimaryKeyConstraint("id", name="pk_group_memberships"),
    )
    op.create_index("ix_group_memberships_contact_id", "group_memberships", ["contact_id"])
    op.create_index(
        "ix_group_memberships_destination_id", "group_memberships", ["destination_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_group_memberships_destination_id", table_name="group_memberships")
    op.drop_index("ix_group_memberships_contact_id", table_name="group_memberships")
    op.drop_table("group_memberships")
    op.drop_table("destinations")

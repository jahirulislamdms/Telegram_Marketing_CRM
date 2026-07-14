"""users and events tables

Revision ID: 0001_users_events
Revises:
Create Date: 2026-07-14
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

# revision identifiers, used by Alembic.
revision: str = "0001_users_events"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# JSONB on PostgreSQL, portable JSON elsewhere.
JSONType = sa.JSON().with_variant(JSONB, "postgresql")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("role", sa.String(length=20), nullable=False, server_default="agent"),
        sa.Column("theme", sa.String(length=10), nullable=False, server_default="dark"),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "role in ('admin','manager','agent')", name="ck_users_role_valid"
        ),
        sa.CheckConstraint("theme in ('dark','light')", name="ck_users_theme_valid"),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column(
            "actor_type", sa.String(length=20), nullable=False, server_default="system"
        ),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("entity_ref", sa.String(length=255), nullable=True),
        sa.Column("meta", JSONType, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_events"),
    )
    op.create_index("ix_events_type", "events", ["type"], unique=False)
    op.create_index("ix_events_created_at", "events", ["created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_events_created_at", table_name="events")
    op.drop_index("ix_events_type", table_name="events")
    op.drop_table("events")
    op.drop_index("ix_users_email", table_name="users")
    op.drop_table("users")

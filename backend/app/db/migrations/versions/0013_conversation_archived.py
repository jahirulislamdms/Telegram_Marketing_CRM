"""add conversations.archived (15.1.i/j)

Revision ID: 0013_conv_archived
Revises: 0012_conv_peer_username
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_conv_archived"
down_revision: Union[str, None] = "0012_conv_peer_username"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column(
            "archived", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )


def downgrade() -> None:
    op.drop_column("conversations", "archived")

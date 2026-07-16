"""add conversations.peer_username (15.1.d)

Revision ID: 0012_conv_peer_username
Revises: 0011_message_media_types
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_conv_peer_username"
down_revision: Union[str, None] = "0011_message_media_types"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "conversations", sa.Column("peer_username", sa.String(length=255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("conversations", "peer_username")

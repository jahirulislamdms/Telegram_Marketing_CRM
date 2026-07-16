"""relax messages.type check to allow media kinds (15.1.b)

Revision ID: 0011_message_media_types
Revises: 0010_referrals
Create Date: 2026-07-16
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0011_message_media_types"
down_revision: Union[str, None] = "0010_referrals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NAME = "ck_messages_message_type_valid"
NEW = "type in ('text','image','voice','link','video','gif','sticker','audio','file')"
OLD = "type in ('text','image','voice','link')"


def _swap(check: str) -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.drop_constraint(NAME, "messages", type_="check")
        op.create_check_constraint(NAME, "messages", check)
    else:
        # SQLite: recreate the table with the new check via batch mode.
        with op.batch_alter_table("messages") as batch:
            batch.drop_constraint(NAME, type_="check")
            batch.create_check_constraint(NAME, check)


def upgrade() -> None:
    _swap(NEW)


def downgrade() -> None:
    # NOTE: downgrade fails if any message already uses a new media type.
    _swap(OLD)

"""add the account's real Telegram identity (tg_user_id / username / first name)

Revision ID: 0017_account_identity
Revises: 0016_contact_notes
Create Date: 2026-07-20

§15.6 shows each account's actual Telegram identity alongside our own label.
Purely additive: three nullable columns, populated from the engine on login and
refreshed on a status check.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0017_account_identity"
down_revision: Union[str, None] = "0016_contact_notes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("tg_user_id", sa.BigInteger(), nullable=True))
    op.add_column("accounts", sa.Column("tg_username", sa.String(length=255), nullable=True))
    op.add_column("accounts", sa.Column("tg_first_name", sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column("accounts", "tg_first_name")
    op.drop_column("accounts", "tg_username")
    op.drop_column("accounts", "tg_user_id")

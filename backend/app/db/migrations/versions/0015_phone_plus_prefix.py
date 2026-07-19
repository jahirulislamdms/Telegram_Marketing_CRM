"""ensure contact phones carry a leading '+' (phone-send fix)

Revision ID: 0015_phone_plus_prefix
Revises: 0014_app_settings
Create Date: 2026-07-16

A phone stored without '+' (e.g. '8801646562267') is indistinguishable from a
Telegram user id, so messaging it failed. Prefix any digit-only phone with '+'.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0015_phone_plus_prefix"
down_revision: Union[str, None] = "0014_app_settings"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # String concat ('+' || phone) and NOT LIKE work on both PostgreSQL and SQLite.
    op.execute(
        "UPDATE contacts SET phone = '+' || phone "
        "WHERE phone IS NOT NULL AND phone <> '' AND phone NOT LIKE '+%'"
    )


def downgrade() -> None:
    # One-way data fix; leaving the '+' in place is harmless.
    pass

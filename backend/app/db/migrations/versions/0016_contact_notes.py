"""add contacts.notes (free-form CRM notes)

Revision ID: 0016_contact_notes
Revises: 0015_phone_plus_prefix
Create Date: 2026-07-19

§15.3 Contacts UX upgrade adds an optional, unbounded notes field to a contact.
Purely additive: nullable Text column, no data change.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0016_contact_notes"
down_revision: Union[str, None] = "0015_phone_plus_prefix"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("notes", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("contacts", "notes")

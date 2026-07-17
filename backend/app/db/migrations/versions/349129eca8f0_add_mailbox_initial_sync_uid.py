"""add mailbox initial_sync_uid

Revision ID: 349129eca8f0
Revises: 82c08cff870f
Create Date: 2026-07-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "349129eca8f0"
down_revision: Union[str, None] = "82c08cff870f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mailboxes", sa.Column("initial_sync_uid", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("mailboxes", "initial_sync_uid")

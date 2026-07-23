"""add mailbox last_poll_error

Revision ID: 16d3bb04e654
Revises: 349129eca8f0
Create Date: 2026-07-23 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "16d3bb04e654"
down_revision: Union[str, None] = "349129eca8f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("mailboxes", sa.Column("last_poll_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("mailboxes", "last_poll_error")

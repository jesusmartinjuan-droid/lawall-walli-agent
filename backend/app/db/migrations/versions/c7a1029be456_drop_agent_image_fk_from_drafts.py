"""drop agent_image fk from drafts

Revision ID: c7a1029be456
Revises: b4d8e21fa093
Create Date: 2026-10-03 00:00:02.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c7a1029be456"
down_revision: Union[str, None] = "b4d8e21fa093"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_constraint("fk_drafts_agent_image_id", "drafts", type_="foreignkey")
    op.drop_column("drafts", "agent_image_id")


def downgrade() -> None:
    op.add_column("drafts", sa.Column("agent_image_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_drafts_agent_image_id", "drafts", "agent_images", ["agent_image_id"], ["id"], ondelete="SET NULL"
    )

"""add agent_image_id to drafts

Revision ID: c3457b8a52f9
Revises: 285f3878a408
Create Date: 2026-09-18 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c3457b8a52f9'
down_revision: Union[str, None] = '285f3878a408'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('drafts', sa.Column('agent_image_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'fk_drafts_agent_image_id', 'drafts', 'agent_images', ['agent_image_id'], ['id'], ondelete='SET NULL'
    )


def downgrade() -> None:
    op.drop_constraint('fk_drafts_agent_image_id', 'drafts', type_='foreignkey')
    op.drop_column('drafts', 'agent_image_id')

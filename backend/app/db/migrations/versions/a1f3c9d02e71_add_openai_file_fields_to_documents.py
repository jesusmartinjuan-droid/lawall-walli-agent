"""add openai file fields to documents

Revision ID: a1f3c9d02e71
Revises: c3457b8a52f9
Create Date: 2026-10-03 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1f3c9d02e71"
down_revision: Union[str, None] = "c3457b8a52f9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("documents", sa.Column("size_bytes", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("documents", sa.Column("openai_file_id", sa.String(length=255), nullable=True))
    op.add_column(
        "documents", sa.Column("openai_file_uploaded_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("documents", sa.Column("openai_upload_error", sa.String(length=2048), nullable=True))
    op.drop_column("documents", "extracted_text")


def downgrade() -> None:
    op.add_column("documents", sa.Column("extracted_text", sa.Text(), nullable=True))
    op.drop_column("documents", "openai_upload_error")
    op.drop_column("documents", "openai_file_uploaded_at")
    op.drop_column("documents", "openai_file_id")
    op.drop_column("documents", "size_bytes")

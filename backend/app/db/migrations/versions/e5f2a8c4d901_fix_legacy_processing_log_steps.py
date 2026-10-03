"""fix legacy processing_log steps

Revision ID: e5f2a8c4d901
Revises: d2e9a7c13f08
Create Date: 2026-10-03 00:00:04.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e5f2a8c4d901"
down_revision: Union[str, None] = "d2e9a7c13f08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # `ProcessingStep.LOAD_DOCUMENTS`/`BUILD_CONTEXT` were merged into a
    # single `ATTACH_FILES` step. The column is a plain VARCHAR
    # (native_enum=False), so old rows with the retired values are never
    # rejected at write time — they just blow up with a LookupError the
    # moment SQLAlchemy tries to read them back into the new Python enum
    # (confirmed in production: /api/dashboard/summary 500ing on exactly
    # this). Existing rows need to be rewritten, not just new ones guarded.
    op.execute(
        "UPDATE processing_logs SET step = 'attach_files' "
        "WHERE step IN ('load_documents', 'build_context')"
    )


def downgrade() -> None:
    # Not reversible: both old steps collapsed into one, so there's no way
    # to know which rows were originally which.
    pass

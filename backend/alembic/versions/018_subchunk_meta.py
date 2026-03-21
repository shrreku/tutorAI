from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "018_subchunk_meta"
down_revision = "017_processing_batch_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sub_chunk",
        sa.Column("enrichment_metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("sub_chunk", "enrichment_metadata")

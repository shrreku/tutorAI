"""add resource and ingestion job ownership

Revision ID: 006_resource_ownership
Revises: h004_consent_training
Create Date: 2026-03-02
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision = "006_resource_ownership"
down_revision = "h004_consent_training"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "resource",
        sa.Column("owner_user_id", UUID(as_uuid=True), sa.ForeignKey("user_profile.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_resource_owner_user_id", "resource", ["owner_user_id"])

    op.add_column(
        "ingestion_job",
        sa.Column("owner_user_id", UUID(as_uuid=True), sa.ForeignKey("user_profile.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_ingestion_job_owner_user_id", "ingestion_job", ["owner_user_id"])

    op.execute(
        """
        UPDATE ingestion_job ij
        SET owner_user_id = r.owner_user_id
        FROM resource r
        WHERE ij.resource_id = r.id
        """
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_job_owner_user_id", table_name="ingestion_job")
    op.drop_column("ingestion_job", "owner_user_id")

    op.drop_index("ix_resource_owner_user_id", table_name="resource")
    op.drop_column("resource", "owner_user_id")

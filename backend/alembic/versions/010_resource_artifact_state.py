"""add resource artifact state table

Revision ID: 010_resource_artifact_state
Revises: 009_staged_ingestion_core
Create Date: 2026-03-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = "010_resource_artifact_state"
down_revision = "009_staged_ingestion_core"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resource_artifact_state",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("resource_id", UUID(as_uuid=True), sa.ForeignKey("resource.id", ondelete="CASCADE"), nullable=True),
        sa.Column("notebook_id", UUID(as_uuid=True), sa.ForeignKey("notebook.id", ondelete="CASCADE"), nullable=True),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_key", sa.String(length=256), nullable=False),
        sa.Column("artifact_kind", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'ready'")),
        sa.Column("version", sa.String(length=64), nullable=False, server_default=sa.text("'1.0'")),
        sa.Column("payload_json", JSONB, nullable=True),
        sa.Column("source_chunk_ids", JSONB, nullable=True),
        sa.Column("content_hash", sa.String(length=128), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("resource_id IS NOT NULL OR notebook_id IS NOT NULL", name="ck_resource_artifact_owner"),
    )
    op.create_index("ix_resource_artifact_state_resource_id", "resource_artifact_state", ["resource_id"])
    op.create_index("ix_resource_artifact_state_notebook_id", "resource_artifact_state", ["notebook_id"])
    op.create_index(
        "ix_resource_artifact_scope_kind",
        "resource_artifact_state",
        ["resource_id", "notebook_id", "scope_type", "scope_key", "artifact_kind"],
    )


def downgrade() -> None:
    op.drop_index("ix_resource_artifact_scope_kind", table_name="resource_artifact_state")
    op.drop_index("ix_resource_artifact_state_notebook_id", table_name="resource_artifact_state")
    op.drop_index("ix_resource_artifact_state_resource_id", table_name="resource_artifact_state")
    op.drop_table("resource_artifact_state")

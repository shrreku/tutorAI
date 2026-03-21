"""Add processing_batch table for phased progressive ingestion.

Revision ID: 017_processing_batch_table
Revises: 016_sub_chunk_table
"""

from alembic import op
import sqlalchemy as sa

revision = "017_processing_batch_table"
down_revision = "016_sub_chunk_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processing_batch",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "resource_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("resource.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("batch_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "status", sa.String(32), nullable=False, server_default="pending"
        ),
        sa.Column("chunk_index_start", sa.Integer, nullable=False, server_default="0"),
        sa.Column("chunk_index_end", sa.Integer, nullable=False, server_default="0"),
        sa.Column("section_headings", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("chunk_ids", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("token_estimate", sa.Integer, nullable=False, server_default="0"),
        # Stage tracking
        sa.Column(
            "ontology_status", sa.String(32), nullable=False, server_default="pending"
        ),
        sa.Column(
            "enrichment_status",
            sa.String(32),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "kb_merge_status", sa.String(32), nullable=False, server_default="pending"
        ),
        sa.Column(
            "graph_merge_status",
            sa.String(32),
            nullable=False,
            server_default="pending",
        ),
        # Readiness flags
        sa.Column(
            "is_retrieval_ready",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "is_study_ready",
            sa.Boolean,
            nullable=False,
            server_default=sa.text("false"),
        ),
        # Results
        sa.Column("concepts_admitted", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "graph_edges_created", sa.Integer, nullable=False, server_default="0"
        ),
        sa.Column("ontology_context", sa.Text, nullable=True),
        sa.Column("result_json", sa.dialects.postgresql.JSONB, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        # Stage timestamps
        sa.Column(
            "ontology_completed_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "enrichment_completed_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "kb_merge_completed_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        # Standard timestamps
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_processing_batch_resource", "processing_batch", ["resource_id"]
    )
    op.create_index(
        "ix_processing_batch_resource_status",
        "processing_batch",
        ["resource_id", "status"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_processing_batch_resource_status", table_name="processing_batch"
    )
    op.drop_index("ix_processing_batch_resource", table_name="processing_batch")
    op.drop_table("processing_batch")

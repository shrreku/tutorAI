"""Add sub_chunk table for fine-grained retrieval.

Revision ID: 016_sub_chunk_table
Revises: 015_alpha_access_request
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

revision = "016_sub_chunk_table"
down_revision = "015_alpha_access_request"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sub_chunk",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "parent_chunk_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("chunk.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "resource_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("resource.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("sub_index", sa.Integer, nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("char_start", sa.Integer, nullable=False),
        sa.Column("char_end", sa.Integer, nullable=False),
        sa.Column("page_start", sa.Integer, nullable=True),
        sa.Column("page_end", sa.Integer, nullable=True),
        sa.Column("embedding", Vector(384), nullable=True),
        sa.Column("embedding_model_id", sa.String(128), nullable=True),
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
    op.create_index("ix_sub_chunk_parent_sub", "sub_chunk", ["parent_chunk_id", "sub_index"])
    op.create_index("ix_sub_chunk_resource", "sub_chunk", ["resource_id"])


def downgrade() -> None:
    op.drop_index("ix_sub_chunk_resource", table_name="sub_chunk")
    op.drop_index("ix_sub_chunk_parent_sub", table_name="sub_chunk")
    op.drop_table("sub_chunk")

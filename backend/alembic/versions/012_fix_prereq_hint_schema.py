"""fix KB table schema mismatches between models and migration 001

Revision ID: 012_fix_prereq_hint_schema
Revises: 011_async_byok_escrow
Create Date: 2026-03-10

Fixes:
- resource_prereq_hint: add support_count, drop confidence/timestamps
- resource_topic_bundle: add support_concepts, prereq_topic_ids,
  rename representative_chunks -> representative_chunk_ids
- resource_topic: add topic_string column
- resource_learning_objective: add objective_text column
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "012_fix_prereq_hint_schema"
down_revision = "011_async_byok_escrow"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── resource_prereq_hint ──
    op.add_column(
        "resource_prereq_hint",
        sa.Column("support_count", sa.Integer(), server_default="0", nullable=True),
    )
    op.drop_column("resource_prereq_hint", "confidence")
    op.drop_column("resource_prereq_hint", "created_at")
    op.drop_column("resource_prereq_hint", "updated_at")

    # ── resource_topic_bundle ──
    # Add columns used by the model but missing from migration 001
    op.add_column(
        "resource_topic_bundle",
        sa.Column("support_concepts", JSONB, nullable=True),
    )
    op.add_column(
        "resource_topic_bundle",
        sa.Column("prereq_topic_ids", JSONB, nullable=True),
    )
    # Rename representative_chunks -> representative_chunk_ids (model column name)
    op.alter_column(
        "resource_topic_bundle",
        "representative_chunks",
        new_column_name="representative_chunk_ids",
    )

    # ── resource_topic ──
    # Model uses topic_string; DB has topic_name from migration 001
    op.add_column(
        "resource_topic",
        sa.Column("topic_string", sa.String(512), nullable=True),
    )
    # Make legacy NOT NULL columns nullable so inserts without them succeed
    op.alter_column("resource_topic", "topic_id", nullable=True)

    # ── resource_learning_objective ──
    # Model uses objective_text; DB has title/description from migration 001
    op.add_column(
        "resource_learning_objective",
        sa.Column("objective_text", sa.Text(), nullable=True),
    )
    # Make legacy NOT NULL columns nullable
    op.alter_column("resource_learning_objective", "objective_id", nullable=True)
    op.alter_column("resource_learning_objective", "title", nullable=True)


def downgrade() -> None:
    # ── resource_learning_objective ──
    op.alter_column("resource_learning_objective", "title", nullable=False)
    op.alter_column("resource_learning_objective", "objective_id", nullable=False)
    op.drop_column("resource_learning_objective", "objective_text")

    # ── resource_topic ──
    op.alter_column("resource_topic", "topic_id", nullable=False)
    op.drop_column("resource_topic", "topic_string")

    # ── resource_topic_bundle ──
    op.alter_column(
        "resource_topic_bundle",
        "representative_chunk_ids",
        new_column_name="representative_chunks",
    )
    op.drop_column("resource_topic_bundle", "prereq_topic_ids")
    op.drop_column("resource_topic_bundle", "support_concepts")

    # ── resource_prereq_hint ──
    op.add_column(
        "resource_prereq_hint",
        sa.Column("confidence", sa.Float(), nullable=True),
    )
    op.add_column(
        "resource_prereq_hint",
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column(
        "resource_prereq_hint",
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.drop_column("resource_prereq_hint", "support_count")

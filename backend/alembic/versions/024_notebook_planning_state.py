"""add notebook planning state table

Revision ID: 024_notebook_planning_state
Revises: 023_seed_curriculum_assignment
Create Date: 2026-04-01
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "024_notebook_planning_state"
down_revision = "023_seed_curriculum_assignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notebook_planning_state",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("uuid_generate_v4()"),
        ),
        sa.Column(
            "notebook_id",
            UUID(as_uuid=True),
            sa.ForeignKey("notebook.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("knowledge_state", JSONB, nullable=True),
        sa.Column("learner_state", JSONB, nullable=True),
        sa.Column("planner_state", JSONB, nullable=True),
        sa.Column("coverage_snapshot", JSONB, nullable=True),
        sa.Column("planning_metadata", JSONB, nullable=True),
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
        "ix_notebook_planning_state_notebook_id",
        "notebook_planning_state",
        ["notebook_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_notebook_planning_state_notebook_id",
        table_name="notebook_planning_state",
    )
    op.drop_table("notebook_planning_state")

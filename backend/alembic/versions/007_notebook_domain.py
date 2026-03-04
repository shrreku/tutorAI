"""add notebook domain tables

Revision ID: 007_notebook_domain
Revises: 006_resource_ownership
Create Date: 2026-03-04
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "007_notebook_domain"
down_revision = "006_resource_ownership"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notebook",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("student_id", UUID(as_uuid=True), sa.ForeignKey("user_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=256), nullable=False),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("target_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("settings_json", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notebook_student_id", "notebook", ["student_id"])

    op.create_table(
        "notebook_resource",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("notebook_id", UUID(as_uuid=True), sa.ForeignKey("notebook.id", ondelete="CASCADE"), nullable=False),
        sa.Column("resource_id", UUID(as_uuid=True), sa.ForeignKey("resource.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False, server_default=sa.text("'supplemental'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("notebook_id", "resource_id", name="uq_notebook_resource_pair"),
    )
    op.create_index("ix_notebook_resource_notebook_id", "notebook_resource", ["notebook_id"])
    op.create_index("ix_notebook_resource_resource_id", "notebook_resource", ["resource_id"])

    op.create_table(
        "notebook_session",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("notebook_id", UUID(as_uuid=True), sa.ForeignKey("notebook.id", ondelete="CASCADE"), nullable=False),
        sa.Column("session_id", UUID(as_uuid=True), sa.ForeignKey("user_session.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mode", sa.String(length=32), nullable=False, server_default=sa.text("'learn'")),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("notebook_id", "session_id", name="uq_notebook_session_pair"),
    )
    op.create_index("ix_notebook_session_notebook_id", "notebook_session", ["notebook_id"])
    op.create_index("ix_notebook_session_session_id", "notebook_session", ["session_id"])

    op.create_table(
        "notebook_progress",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("notebook_id", UUID(as_uuid=True), sa.ForeignKey("notebook.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("mastery_snapshot", JSONB, nullable=True),
        sa.Column("objective_progress_snapshot", JSONB, nullable=True),
        sa.Column("weak_concepts_snapshot", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notebook_progress_notebook_id", "notebook_progress", ["notebook_id"])

    op.create_table(
        "notebook_artifact",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("notebook_id", UUID(as_uuid=True), sa.ForeignKey("notebook.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", sa.String(length=64), nullable=False),
        sa.Column("payload_json", JSONB, nullable=False),
        sa.Column("source_session_ids", JSONB, nullable=True),
        sa.Column("source_resource_ids", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notebook_artifact_notebook_id", "notebook_artifact", ["notebook_id"])


def downgrade() -> None:
    op.drop_index("ix_notebook_artifact_notebook_id", table_name="notebook_artifact")
    op.drop_table("notebook_artifact")

    op.drop_index("ix_notebook_progress_notebook_id", table_name="notebook_progress")
    op.drop_table("notebook_progress")

    op.drop_index("ix_notebook_session_session_id", table_name="notebook_session")
    op.drop_index("ix_notebook_session_notebook_id", table_name="notebook_session")
    op.drop_table("notebook_session")

    op.drop_index("ix_notebook_resource_resource_id", table_name="notebook_resource")
    op.drop_index("ix_notebook_resource_notebook_id", table_name="notebook_resource")
    op.drop_table("notebook_resource")

    op.drop_index("ix_notebook_student_id", table_name="notebook")
    op.drop_table("notebook")

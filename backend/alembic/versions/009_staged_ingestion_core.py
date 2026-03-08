"""add staged-ingestion capability fields

Revision ID: 009_staged_ingestion_core
Revises: 008_add_password_hash
Create Date: 2026-03-08
"""

import json

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "009_staged_ingestion_core"
down_revision = "008_add_password_hash"
branch_labels = None
depends_on = None


DEFAULT_CAPABILITIES = {
    "study_ready": False,
    "vector_search_ready": False,
    "basic_tutoring_ready": False,
    "can_search": False,
    "can_answer_doubts": False,
    "can_generate_basic_practice": False,
    "can_tutor_basic": False,
    "can_start_learn_session": False,
    "can_start_practice_session": False,
    "can_start_revision_session": False,
    "resource_profile_ready": False,
    "has_resource_profile": False,
    "topic_prepare_ready": False,
    "concepts_ready": False,
    "has_concepts": False,
    "has_topic_bundles": False,
    "has_prereq_graph": False,
    "graph_ready": False,
    "has_curriculum_artifacts": False,
    "curriculum_ready": False,
    "is_graph_synced": False,
    "neo4j_synced": False,
}


STUDY_READY_SQL = """
jsonb_build_object(
    'study_ready', true,
    'vector_search_ready', true,
    'basic_tutoring_ready', true,
    'can_search', true,
    'can_answer_doubts', true,
    'can_generate_basic_practice', true,
    'can_tutor_basic', true,
    'can_start_learn_session', false,
    'can_start_practice_session', false,
    'can_start_revision_session', false,
    'resource_profile_ready', false,
    'has_resource_profile', false,
    'topic_prepare_ready', false,
    'concepts_ready', false,
    'has_concepts', false,
    'has_topic_bundles', false,
    'has_prereq_graph', false,
    'graph_ready', false,
    'has_curriculum_artifacts', false,
    'curriculum_ready', false,
    'is_graph_synced', false,
    'neo4j_synced', false
)
"""


def upgrade() -> None:
    op.add_column(
        "resource",
        sa.Column(
            "capabilities_json",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "resource",
        sa.Column("processing_profile", sa.String(length=64), nullable=True, server_default=sa.text("'core_only'")),
    )
    op.add_column("resource", sa.Column("study_ready_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("resource", sa.Column("tutoring_ready_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("resource", sa.Column("curriculum_ready_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("resource", sa.Column("graph_ready_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column(
        "ingestion_job",
        sa.Column("job_kind", sa.String(length=64), nullable=False, server_default=sa.text("'core_ingest'")),
    )
    op.add_column("ingestion_job", sa.Column("requested_capability", sa.String(length=64), nullable=True))
    op.add_column("ingestion_job", sa.Column("scope_type", sa.String(length=32), nullable=True))
    op.add_column("ingestion_job", sa.Column("scope_key", sa.String(length=256), nullable=True))

    op.execute(
        f"""
        UPDATE resource
        SET capabilities_json = CASE
            WHEN status = 'ready' THEN {STUDY_READY_SQL}
            ELSE '{json.dumps(DEFAULT_CAPABILITIES)}'::jsonb
        END,
            processing_profile = COALESCE(processing_profile, 'core_only'),
            study_ready_at = CASE WHEN status = 'ready' THEN COALESCE(processed_at, NOW()) ELSE study_ready_at END
        """
    )

    op.execute(
        """
        UPDATE ingestion_job
        SET requested_capability = COALESCE(requested_capability, 'study_ready'),
            scope_type = COALESCE(scope_type, 'resource'),
            scope_key = COALESCE(scope_key, resource_id::text)
        """
    )


def downgrade() -> None:
    op.drop_column("ingestion_job", "scope_key")
    op.drop_column("ingestion_job", "scope_type")
    op.drop_column("ingestion_job", "requested_capability")
    op.drop_column("ingestion_job", "job_kind")

    op.drop_column("resource", "graph_ready_at")
    op.drop_column("resource", "curriculum_ready_at")
    op.drop_column("resource", "tutoring_ready_at")
    op.drop_column("resource", "study_ready_at")
    op.drop_column("resource", "processing_profile")
    op.drop_column("resource", "capabilities_json")

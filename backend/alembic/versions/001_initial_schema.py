"""initial_schema

Revision ID: 001
Revises: 
Create Date: 2026-02-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from pgvector.sqlalchemy import Vector

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create extensions
    op.execute('CREATE EXTENSION IF NOT EXISTS vector')
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')
    
    # Create resource table
    op.create_table(
        'resource',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('filename', sa.String(512), nullable=False),
        sa.Column('topic', sa.String(256), nullable=True),
        sa.Column('status', sa.String(32), nullable=False, server_default='processing'),
        sa.Column('file_path_or_uri', sa.String(1024), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('processed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pipeline_version', sa.String(64), nullable=True),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    
    # Create chunk table
    op.create_table(
        'chunk',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('resource.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('text', sa.Text, nullable=False),
        sa.Column('section_heading', sa.String(512), nullable=True),
        sa.Column('chunk_index', sa.Integer, nullable=False),
        sa.Column('page_start', sa.Integer, nullable=True),
        sa.Column('page_end', sa.Integer, nullable=True),
        sa.Column('pedagogy_role', sa.String(64), nullable=True),
        sa.Column('difficulty', sa.String(32), nullable=True),
        sa.Column('embedding', Vector(384), nullable=True),
        sa.Column('enrichment_metadata', postgresql.JSONB, nullable=True),
        sa.Column('embedding_model_id', sa.String(128), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint('resource_id', 'chunk_index', name='uq_chunk_resource_index'),
    )
    op.create_index('ix_chunk_resource_chunk_index', 'chunk', ['resource_id', 'chunk_index'])
    
    # Create chunk_concept table
    op.create_table(
        'chunk_concept',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('chunk_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('chunk.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('concept_id', sa.String(256), nullable=False, index=True),
        sa.Column('role', sa.String(32), nullable=False, server_default='mentions'),
    )
    op.create_index('ix_chunk_concept_chunk_concept', 'chunk_concept', ['chunk_id', 'concept_id'])
    
    # Create formula table
    op.create_table(
        'formula',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('resource.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('name', sa.String(256), nullable=True),
        sa.Column('expression', sa.Text, nullable=False),
        sa.Column('expression_plain', sa.Text, nullable=True),
        sa.Column('variables', postgresql.JSONB, nullable=True),
        sa.Column('concept_ids', postgresql.JSONB, nullable=True),
        sa.Column('source_chunk_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('chunk.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    
    # Create resource_concept_stats table
    op.create_table(
        'resource_concept_stats',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('resource.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('concept_id', sa.String(256), nullable=False, index=True),
        sa.Column('teach_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('mention_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('chunk_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('avg_quality', sa.Float, nullable=True),
        sa.Column('position_mean', sa.Float, nullable=True),
        sa.Column('position_std', sa.Float, nullable=True),
        sa.Column('source_types', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint('resource_id', 'concept_id', name='uq_resource_concept_stats'),
    )
    
    # Create resource_concept_evidence table
    op.create_table(
        'resource_concept_evidence',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('resource.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('concept_id', sa.String(256), nullable=False, index=True),
        sa.Column('chunk_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('chunk.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('role', sa.String(32), nullable=False),
        sa.Column('weight', sa.Float, nullable=False, server_default='1.0'),
        sa.Column('quality_score', sa.Float, nullable=True),
        sa.Column('position_index', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index('ix_evidence_resource_concept', 'resource_concept_evidence', ['resource_id', 'concept_id'])
    
    # Create resource_concept_graph table
    op.create_table(
        'resource_concept_graph',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('resource.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('source_concept_id', sa.String(256), nullable=False, index=True),
        sa.Column('target_concept_id', sa.String(256), nullable=False, index=True),
        sa.Column('assoc_weight', sa.Float, nullable=False),
        sa.Column('dir_forward', sa.Float, nullable=True),
        sa.Column('dir_backward', sa.Float, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint('resource_id', 'source_concept_id', 'target_concept_id', name='uq_resource_concept_graph'),
    )
    
    # Create resource_bundle table
    op.create_table(
        'resource_bundle',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('resource.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('primary_concept_id', sa.String(256), nullable=False, index=True),
        sa.Column('support_concepts', postgresql.JSONB, nullable=True),
        sa.Column('prereq_hints', postgresql.JSONB, nullable=True),
        sa.Column('evidence_prototypes', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint('resource_id', 'primary_concept_id', name='uq_resource_bundle'),
    )
    
    # Create resource_topic_bundle table
    op.create_table(
        'resource_topic_bundle',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('resource.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('topic_id', sa.String(256), nullable=False),
        sa.Column('topic_name', sa.String(512), nullable=True),
        sa.Column('primary_concepts', postgresql.JSONB, nullable=True),
        sa.Column('representative_chunks', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    
    # Create resource_topic table
    op.create_table(
        'resource_topic',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('resource.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('topic_id', sa.String(256), nullable=False),
        sa.Column('topic_name', sa.String(512), nullable=True),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('concept_ids', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    
    # Create resource_learning_objective table
    op.create_table(
        'resource_learning_objective',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('resource.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('objective_id', sa.String(256), nullable=False),
        sa.Column('title', sa.String(512), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('concept_scope', postgresql.JSONB, nullable=True),
        sa.Column('success_criteria', postgresql.JSONB, nullable=True),
        sa.Column('phase_skeleton', postgresql.JSONB, nullable=True),
        sa.Column('estimated_turns', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    
    # Create resource_prereq_hint table
    op.create_table(
        'resource_prereq_hint',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('resource.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('source_concept_id', sa.String(256), nullable=False, index=True),
        sa.Column('target_concept_id', sa.String(256), nullable=False, index=True),
        sa.Column('confidence', sa.Float, nullable=True),
        sa.Column('sources', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    
    # Create user_profile table
    op.create_table(
        'user_profile',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('external_id', sa.String(256), nullable=True, unique=True),
        sa.Column('display_name', sa.String(256), nullable=True),
        sa.Column('email', sa.String(512), nullable=True),
        sa.Column('global_mastery', postgresql.JSONB, nullable=True),
        sa.Column('preferences', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    
    # Create user_session table
    op.create_table(
        'user_session',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('user_profile.id', ondelete='CASCADE'), nullable=True, index=True),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('resource.id', ondelete='SET NULL'), nullable=True, index=True),
        sa.Column('status', sa.String(32), nullable=False, server_default='active'),
        sa.Column('plan_state', postgresql.JSONB, nullable=True),
        sa.Column('mastery', postgresql.JSONB, nullable=True),
        sa.Column('token_usage', postgresql.JSONB, nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    
    # Create tutor_turn table
    op.create_table(
        'tutor_turn',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('user_session.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('turn_index', sa.Integer, nullable=False),
        sa.Column('student_message', sa.Text, nullable=True),
        sa.Column('tutor_response', sa.Text, nullable=True),
        sa.Column('tutor_question', sa.Text, nullable=True),
        sa.Column('curriculum_phase_index', sa.Integer, nullable=True),
        sa.Column('current_step', sa.String(64), nullable=True),
        sa.Column('target_concepts', postgresql.JSONB, nullable=True),
        sa.Column('pedagogical_action', sa.String(64), nullable=True),
        sa.Column('progression_decision', sa.Integer, nullable=True),
        sa.Column('policy_output', postgresql.JSONB, nullable=True),
        sa.Column('evaluator_output', postgresql.JSONB, nullable=True),
        sa.Column('retrieved_chunks', postgresql.JSONB, nullable=True),
        sa.Column('mastery_before', postgresql.JSONB, nullable=True),
        sa.Column('mastery_after', postgresql.JSONB, nullable=True),
        sa.Column('rl_reward', sa.Float, nullable=True),
        sa.Column('rl_state_embedding', Vector(384), nullable=True),
        sa.Column('rl_action_embedding', Vector(384), nullable=True),
        sa.Column('token_count', sa.Integer, nullable=True),
        sa.Column('latency_ms', sa.Integer, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.UniqueConstraint('session_id', 'turn_index', name='uq_tutor_turn_session_index'),
    )
    
    # Create ingestion_job table
    op.create_table(
        'ingestion_job',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('resource_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('resource.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('status', sa.String(32), nullable=False, server_default='pending'),
        sa.Column('current_stage', sa.String(64), nullable=True),
        sa.Column('stages_completed', postgresql.JSONB, nullable=True),
        sa.Column('progress_percent', sa.Integer, server_default='0'),
        sa.Column('retry_count', sa.Integer, server_default='0'),
        sa.Column('max_retries', sa.Integer, server_default='3'),
        sa.Column('error_message', sa.Text, nullable=True),
        sa.Column('error_stage', sa.String(64), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('metrics', postgresql.JSONB, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    
    # Create session_feedback_entry table
    op.create_table(
        'session_feedback_entry',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('session_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('user_session.id', ondelete='CASCADE'), nullable=False, index=True),
        sa.Column('turn_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('tutor_turn.id', ondelete='SET NULL'), nullable=True),
        sa.Column('feedback_type', sa.String(64), nullable=False),
        sa.Column('rating', sa.Integer, nullable=True),
        sa.Column('comment', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    
    # Create api_key table
    op.create_table(
        'api_key',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('uuid_generate_v4()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('user_profile.id', ondelete='CASCADE'), nullable=True),
        sa.Column('key_hash', sa.String(512), nullable=False, unique=True),
        sa.Column('name', sa.String(256), nullable=True),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('rate_limit_rpm', sa.Integer, nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    
    # Create HNSW index for vector similarity search
    op.execute('CREATE INDEX IF NOT EXISTS ix_chunk_embedding_hnsw ON chunk USING hnsw (embedding vector_cosine_ops)')
    op.execute('CREATE INDEX IF NOT EXISTS ix_tutor_turn_state_embedding_hnsw ON tutor_turn USING hnsw (rl_state_embedding vector_cosine_ops)')


def downgrade() -> None:
    op.drop_table('api_key')
    op.drop_table('session_feedback_entry')
    op.drop_table('ingestion_job')
    op.drop_table('tutor_turn')
    op.drop_table('user_session')
    op.drop_table('user_profile')
    op.drop_table('resource_prereq_hint')
    op.drop_table('resource_learning_objective')
    op.drop_table('resource_topic')
    op.drop_table('resource_topic_bundle')
    op.drop_table('resource_bundle')
    op.drop_table('resource_concept_graph')
    op.drop_table('resource_concept_evidence')
    op.drop_table('resource_concept_stats')
    op.drop_table('formula')
    op.drop_table('chunk_concept')
    op.drop_table('chunk')
    op.drop_table('resource')

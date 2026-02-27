"""Add ontological fields to knowledge base tables

Revision ID: 002_ontological
Revises: 001_initial_schema
Create Date: 2026-02-04

This migration adds:
- concept_type, bloom_level, importance_score to resource_concept_stats
- relation_type, confidence, source to resource_concept_graph
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002'
down_revision = '001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add ontological metadata fields to resource_concept_stats
    op.add_column(
        'resource_concept_stats',
        sa.Column('concept_type', sa.String(32), nullable=True)
    )
    op.add_column(
        'resource_concept_stats',
        sa.Column('bloom_level', sa.String(32), nullable=True)
    )
    op.add_column(
        'resource_concept_stats',
        sa.Column('importance_score', sa.Float(), nullable=True)
    )
    
    # Add typed relationship fields to resource_concept_graph
    op.add_column(
        'resource_concept_graph',
        sa.Column('relation_type', sa.String(32), nullable=False, server_default='RELATED_TO')
    )
    op.add_column(
        'resource_concept_graph',
        sa.Column('confidence', sa.Float(), nullable=False, server_default='0.5')
    )
    op.add_column(
        'resource_concept_graph',
        sa.Column('source', sa.String(32), nullable=False, server_default='cooccurrence')
    )
    
    # Add index for relation_type queries
    op.create_index(
        'ix_resource_concept_graph_relation',
        'resource_concept_graph',
        ['resource_id', 'relation_type']
    )


def downgrade() -> None:
    # Remove index
    op.drop_index('ix_resource_concept_graph_relation', table_name='resource_concept_graph')
    
    # Remove columns from resource_concept_graph
    op.drop_column('resource_concept_graph', 'source')
    op.drop_column('resource_concept_graph', 'confidence')
    op.drop_column('resource_concept_graph', 'relation_type')
    
    # Remove columns from resource_concept_stats
    op.drop_column('resource_concept_stats', 'importance_score')
    op.drop_column('resource_concept_stats', 'bloom_level')
    op.drop_column('resource_concept_stats', 'concept_type')

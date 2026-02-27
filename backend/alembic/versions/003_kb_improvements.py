"""KB improvements: distributions, topo_order, specificity

Revision ID: 003
Revises: 002
Create Date: 2025-01-01

Adds:
- type_distribution, bloom_distribution, difficulty_distribution,
  pedagogy_distribution, topo_order to resource_concept_stats
- specificity to resource_learning_objective
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Proportional distributions on resource_concept_stats
    op.add_column(
        'resource_concept_stats',
        sa.Column('type_distribution', JSONB, nullable=True),
    )
    op.add_column(
        'resource_concept_stats',
        sa.Column('bloom_distribution', JSONB, nullable=True),
    )
    op.add_column(
        'resource_concept_stats',
        sa.Column('difficulty_distribution', JSONB, nullable=True),
    )
    op.add_column(
        'resource_concept_stats',
        sa.Column('pedagogy_distribution', JSONB, nullable=True),
    )
    op.add_column(
        'resource_concept_stats',
        sa.Column('topo_order', sa.Integer(), nullable=True),
    )

    # Specificity on learning objectives
    op.add_column(
        'resource_learning_objective',
        sa.Column('specificity', sa.String(32), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('resource_learning_objective', 'specificity')
    op.drop_column('resource_concept_stats', 'topo_order')
    op.drop_column('resource_concept_stats', 'pedagogy_distribution')
    op.drop_column('resource_concept_stats', 'difficulty_distribution')
    op.drop_column('resource_concept_stats', 'bloom_distribution')
    op.drop_column('resource_concept_stats', 'type_distribution')

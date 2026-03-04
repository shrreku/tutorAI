"""add consent_training to user_session

Revision ID: h004_consent_training
Revises: 005_credits_domain
"""
from alembic import op
import sqlalchemy as sa

revision = "h004_consent_training"
down_revision = "005_credits_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_session",
        sa.Column("consent_training", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def downgrade() -> None:
    op.drop_column("user_session", "consent_training")

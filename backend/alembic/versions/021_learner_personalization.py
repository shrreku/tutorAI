"""Add learner personalization columns.

PROD-021: Structured learner profile model.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = "021_learner_personalization"
down_revision = "020_llamaparse_page_allowance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # User-level learning preferences (account-wide defaults)
    op.add_column(
        "user_profile",
        sa.Column("learning_preferences", JSONB, nullable=True),
    )

    # RL research: personalization consent (separate from research consent)
    op.add_column(
        "user_profile",
        sa.Column(
            "consent_personalization",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )

    # RL research: personalization interaction log for reward signals
    op.add_column(
        "user_session",
        sa.Column("personalization_snapshot", JSONB, nullable=True),
    )

    # Remove server defaults after backfill
    op.alter_column("user_profile", "consent_personalization", server_default=None)


def downgrade() -> None:
    op.drop_column("user_session", "personalization_snapshot")
    op.drop_column("user_profile", "consent_personalization")
    op.drop_column("user_profile", "learning_preferences")

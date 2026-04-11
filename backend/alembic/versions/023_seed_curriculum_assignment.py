"""Seed missing curriculum task assignment.

PROD-023: Ensure the sessions launcher can resolve curriculum model options
from the strict task-model endpoint instead of hitting a 404.
"""

from alembic import op


revision = "023_seed_curriculum_assignment"
down_revision = "022_seed_artifact_assignment"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO task_model_assignment (
            id,
            task_type,
            default_model_id,
            fallback_model_ids,
            allowed_model_ids,
            user_override_allowed,
            rollout_state,
            beta_only
        )
        VALUES (
            gen_random_uuid(),
            'curriculum',
            'google/gemini-3-flash-preview',
            '["openai/gpt-5-mini"]'::jsonb,
            '[
                "google/gemini-3-flash-preview",
                "google/gemini-3.1-flash-lite-preview",
                "openai/gpt-5-mini"
            ]'::jsonb,
            true,
            'active',
            false
        )
        ON CONFLICT (task_type) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM task_model_assignment
        WHERE task_type = 'curriculum'
        """
    )

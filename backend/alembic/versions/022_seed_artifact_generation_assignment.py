"""Seed missing artifact generation task assignment.

PROD-022: Ensure the task-model registry contains the notebook artifact generation
assignment so the model selection UI can load a real task row instead of
falling back.
"""

from alembic import op


revision = "022_seed_artifact_assignment"
down_revision = "021_learner_personalization"
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
            'artifact_generation',
            'google/gemini-3-flash-preview',
            '["openai/gpt-5-mini"]'::jsonb,
            '[
                "google/gemini-3.1-flash-lite-preview",
                "mercury/mercury-coder-small-beta",
                "alibaba/qwen-3.5-9b",
                "alibaba/seed-coder-2.0-mini",
                "anthropic/claude-haiku-4.5",
                "google/gemini-3-flash-preview",
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
        WHERE task_type = 'artifact_generation'
        """
    )

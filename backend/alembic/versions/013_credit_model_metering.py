"""Credits, model selection, and metering tables.

Revision ID: 013_credits_model_selection_metering
Revises: 012_fix_prereq_hint_schema
Create Date: 2026-03-11

Adds:
- model_pricing            (CM-001)
- task_model_assignment     (CM-002)
- billing_operation         (CM-003)
- billing_usage_line        (CM-003)
- model_task_health         (CM-010)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "013_credit_model_metering"
down_revision = "012_fix_prereq_hint_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── model_pricing (CM-001) ──
    op.create_table(
        "model_pricing",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("model_id", sa.String(256), nullable=False, unique=True, index=True),
        sa.Column("provider_name", sa.String(128), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("model_class", sa.String(64), nullable=False),
        sa.Column("input_usd_per_million", sa.Float, nullable=False, server_default="0"),
        sa.Column("output_usd_per_million", sa.Float, nullable=False, server_default="0"),
        sa.Column("cache_write_usd_per_million", sa.Float, nullable=True),
        sa.Column("cache_read_usd_per_million", sa.Float, nullable=True),
        sa.Column("search_usd_per_unit", sa.Float, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("is_user_selectable", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("supports_structured_output", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("supports_long_context", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("supports_byok", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Seed initial curated models
    op.execute("""
        INSERT INTO model_pricing (id, model_id, provider_name, display_name, model_class,
            input_usd_per_million, output_usd_per_million, cache_read_usd_per_million,
            is_active, is_user_selectable, supports_structured_output, supports_long_context)
        VALUES
            (gen_random_uuid(), 'google/gemini-3.1-flash-lite-preview', 'google', 'Gemini 3.1 Flash Lite', 'economy',
             0.015, 0.06, 0.004, true, true, true, true),
            (gen_random_uuid(), 'mercury/mercury-coder-small-beta', 'mercury', 'Mercury 2', 'economy',
             0.025, 0.10, NULL, true, true, false, false),
            (gen_random_uuid(), 'alibaba/seed-coder-2.0-mini', 'alibaba', 'Seed 2.0 Mini', 'economy',
             0.015, 0.06, NULL, true, true, true, false),
            (gen_random_uuid(), 'alibaba/qwen-3.5-9b', 'alibaba', 'Qwen 3.5 9B', 'economy',
             0.02, 0.06, NULL, true, true, true, false),
            (gen_random_uuid(), 'openai/gpt-5-mini', 'openai', 'GPT-5 Mini', 'standard',
             0.40, 1.60, 0.10, true, true, true, true),
            (gen_random_uuid(), 'google/gemini-3-flash-preview', 'google', 'Gemini 3 Flash', 'standard',
             0.10, 0.40, 0.025, true, true, true, true),
            (gen_random_uuid(), 'anthropic/claude-haiku-4.5', 'anthropic', 'Claude Haiku 4.5', 'premium_small',
             1.00, 5.00, 0.10, true, true, true, true)
    """)

    # ── task_model_assignment (CM-002) ──
    op.create_table(
        "task_model_assignment",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("task_type", sa.String(128), nullable=False, unique=True, index=True),
        sa.Column("default_model_id", sa.String(256), nullable=False),
        sa.Column("fallback_model_ids", JSONB, nullable=True),
        sa.Column("allowed_model_ids", JSONB, nullable=True),
        sa.Column("user_override_allowed", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("rollout_state", sa.String(64), nullable=False, server_default=sa.text("'active'")),
        sa.Column("beta_only", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Seed task assignments
    op.execute("""
        INSERT INTO task_model_assignment (id, task_type, default_model_id, fallback_model_ids, allowed_model_ids, user_override_allowed)
        VALUES
            (gen_random_uuid(), 'ingestion_ontology', 'google/gemini-3-flash-preview',
             '["openai/gpt-5-mini"]'::jsonb,
             '["google/gemini-3-flash-preview","openai/gpt-5-mini","anthropic/claude-haiku-4.5"]'::jsonb, false),
            (gen_random_uuid(), 'ingestion_enrichment', 'google/gemini-3.1-flash-lite-preview',
             '["google/gemini-3-flash-preview"]'::jsonb,
             '["google/gemini-3.1-flash-lite-preview","google/gemini-3-flash-preview"]'::jsonb, false),
            (gen_random_uuid(), 'session_curriculum', 'google/gemini-3-flash-preview',
             '["openai/gpt-5-mini"]'::jsonb,
             '["google/gemini-3-flash-preview","openai/gpt-5-mini"]'::jsonb, false),
            (gen_random_uuid(), 'tutor_policy', 'google/gemini-3-flash-preview',
             '["openai/gpt-5-mini"]'::jsonb,
             '["google/gemini-3-flash-preview","openai/gpt-5-mini","google/gemini-3.1-flash-lite-preview"]'::jsonb, true),
            (gen_random_uuid(), 'tutor_response', 'google/gemini-3-flash-preview',
             '["openai/gpt-5-mini"]'::jsonb,
             '["google/gemini-3-flash-preview","openai/gpt-5-mini","google/gemini-3.1-flash-lite-preview","anthropic/claude-haiku-4.5"]'::jsonb, true),
            (gen_random_uuid(), 'tutor_evaluation', 'google/gemini-3-flash-preview',
             '["openai/gpt-5-mini"]'::jsonb,
             '["google/gemini-3-flash-preview","openai/gpt-5-mini"]'::jsonb, false),
            (gen_random_uuid(), 'tutor_safety', 'google/gemini-3-flash-preview',
             '["openai/gpt-5-mini"]'::jsonb,
             '["google/gemini-3-flash-preview","openai/gpt-5-mini"]'::jsonb, false),
            (gen_random_uuid(), 'tutor_summary', 'google/gemini-3-flash-preview',
             '["openai/gpt-5-mini"]'::jsonb,
             '["google/gemini-3-flash-preview","openai/gpt-5-mini"]'::jsonb, false),
            (gen_random_uuid(), 'artifact_notes', 'google/gemini-3.1-flash-lite-preview',
             '["google/gemini-3-flash-preview"]'::jsonb,
             '["google/gemini-3.1-flash-lite-preview","google/gemini-3-flash-preview","openai/gpt-5-mini"]'::jsonb, true),
            (gen_random_uuid(), 'artifact_flashcards', 'google/gemini-3.1-flash-lite-preview',
             '["google/gemini-3-flash-preview"]'::jsonb,
             '["google/gemini-3.1-flash-lite-preview","google/gemini-3-flash-preview","openai/gpt-5-mini"]'::jsonb, true),
            (gen_random_uuid(), 'artifact_quiz', 'google/gemini-3.1-flash-lite-preview',
             '["google/gemini-3-flash-preview"]'::jsonb,
             '["google/gemini-3.1-flash-lite-preview","google/gemini-3-flash-preview","openai/gpt-5-mini"]'::jsonb, true),
            (gen_random_uuid(), 'artifact_revision_plan', 'google/gemini-3.1-flash-lite-preview',
             '["google/gemini-3-flash-preview"]'::jsonb,
             '["google/gemini-3.1-flash-lite-preview","google/gemini-3-flash-preview","openai/gpt-5-mini"]'::jsonb, true)
    """)

    # ── billing_operation (CM-003) ──
    op.create_table(
        "billing_operation",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("user_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operation_type", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("resource_id", sa.String(256), nullable=True),
        sa.Column("session_id", sa.String(256), nullable=True),
        sa.Column("artifact_id", sa.String(256), nullable=True),
        sa.Column("selected_model_id", sa.String(256), nullable=True),
        sa.Column("routed_model_id", sa.String(256), nullable=True),
        sa.Column("reroute_reason", sa.Text, nullable=True),
        sa.Column("estimate_credits_low", sa.BigInteger, nullable=True),
        sa.Column("estimate_credits_high", sa.BigInteger, nullable=True),
        sa.Column("reserved_credits", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("final_credits", sa.BigInteger, nullable=True),
        sa.Column("final_usd", sa.Float, nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_billing_op_user_created", "billing_operation", ["user_id", "created_at"])
    op.create_index("ix_billing_op_type_status", "billing_operation", ["operation_type", "status"])

    # ── billing_usage_line (CM-003) ──
    op.create_table(
        "billing_usage_line",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("operation_id", UUID(as_uuid=True), sa.ForeignKey("billing_operation.id", ondelete="CASCADE"), nullable=False),
        sa.Column("task_type", sa.String(128), nullable=False),
        sa.Column("model_id", sa.String(256), nullable=False),
        sa.Column("provider_name", sa.String(128), nullable=True),
        sa.Column("input_tokens", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("cache_write_tokens", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("cache_read_tokens", sa.BigInteger, nullable=False, server_default="0"),
        sa.Column("tool_units", sa.Integer, nullable=False, server_default="0"),
        sa.Column("raw_usd", sa.Float, nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'recorded'")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_billing_usage_line_op", "billing_usage_line", ["operation_id"])

    # ── model_task_health (CM-010) ──
    op.create_table(
        "model_task_health",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("model_id", sa.String(256), nullable=False),
        sa.Column("task_type", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default=sa.text("'healthy'")),
        sa.Column("consecutive_errors", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rolling_error_rate", sa.Float, nullable=False, server_default="0"),
        sa.Column("cooldown_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(128), nullable=True),
        sa.Column("last_error_summary", sa.Text, nullable=True),
        sa.Column("manual_override_reason", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_model_task_health_lookup", "model_task_health", ["model_id", "task_type"], unique=True)

    # ── Add model_preferences to user_profile ──
    op.add_column("user_profile", sa.Column("model_preferences", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("user_profile", "model_preferences")
    op.drop_table("model_task_health")
    op.drop_table("billing_usage_line")
    op.drop_table("billing_operation")
    op.drop_table("task_model_assignment")
    op.drop_table("model_pricing")

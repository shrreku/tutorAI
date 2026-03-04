"""add credits domain tables

Revision ID: 005_credits_domain
Revises: 003_kb_improvements
Create Date: 2026-03-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "005_credits_domain"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # credit_account
    op.create_table(
        "credit_account",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("user_profile.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("balance", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("lifetime_granted", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("lifetime_used", sa.BigInteger(), nullable=False, server_default=sa.text("0")),
        sa.Column("plan_tier", sa.String(64), nullable=False, server_default=sa.text("'free_research'")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_credit_account_user_id", "credit_account", ["user_id"])

    # credit_grant
    op.create_table(
        "credit_grant",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("credit_account.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.BigInteger(), nullable=False),
        sa.Column("remaining", sa.BigInteger(), nullable=False),
        sa.Column("source", sa.String(64), nullable=False, server_default=sa.text("'monthly_grant'")),
        sa.Column("memo", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_credit_grant_account_id", "credit_grant", ["account_id"])

    # credit_ledger_entry
    op.create_table(
        "credit_ledger_entry",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("credit_account.id", ondelete="CASCADE"), nullable=False),
        sa.Column("entry_type", sa.String(32), nullable=False),
        sa.Column("delta", sa.BigInteger(), nullable=False),
        sa.Column("balance_after", sa.BigInteger(), nullable=False),
        sa.Column("idempotency_key", sa.String(256), nullable=True, unique=True),
        sa.Column("reference_type", sa.String(64), nullable=True),
        sa.Column("reference_id", sa.String(256), nullable=True),
        sa.Column("metadata", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_credit_ledger_entry_account_id", "credit_ledger_entry", ["account_id"])
    op.create_index("ix_credit_ledger_created", "credit_ledger_entry", ["account_id", "created_at"])

    # model_multiplier
    op.create_table(
        "model_multiplier",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("model_id", sa.String(256), nullable=False, unique=True),
        sa.Column("input_multiplier", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("output_multiplier", sa.Float(), nullable=False, server_default=sa.text("1.5")),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    # Seed default model multipliers
    op.execute("""
        INSERT INTO model_multiplier (id, model_id, input_multiplier, output_multiplier, description)
        VALUES
            (gen_random_uuid(), 'google/gemini-3-flash-preview', 1.0, 1.5, 'Gemini Flash 3 Preview'),
            (gen_random_uuid(), 'google/gemini-2.5-flash-lite', 0.5, 0.75, 'Gemini Flash Lite (cheap)'),
            (gen_random_uuid(), 'gpt-4o', 2.5, 5.0, 'OpenAI GPT-4o'),
            (gen_random_uuid(), 'gpt-4o-mini', 0.5, 1.0, 'OpenAI GPT-4o Mini')
    """)


def downgrade() -> None:
    op.drop_table("model_multiplier")
    op.drop_table("credit_ledger_entry")
    op.drop_table("credit_grant")
    op.drop_table("credit_account")

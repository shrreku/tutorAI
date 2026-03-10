"""add async byok escrow table

Revision ID: 011_async_byok_escrow
Revises: 010_resource_artifact_state
Create Date: 2026-03-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = "011_async_byok_escrow"
down_revision = "010_resource_artifact_state"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "async_byok_escrow",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("uuid_generate_v4()")),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("user_profile.id", ondelete="CASCADE"), nullable=False),
        sa.Column("purpose_type", sa.String(length=64), nullable=False),
        sa.Column("purpose_id", sa.String(length=256), nullable=False),
        sa.Column("scope_type", sa.String(length=32), nullable=False),
        sa.Column("scope_key", sa.String(length=256), nullable=False),
        sa.Column("provider_name", sa.String(length=64), nullable=True),
        sa.Column("ciphertext_blob", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("wrapped_dek", sa.Text(), nullable=False),
        sa.Column("key_backend", sa.String(length=32), nullable=False),
        sa.Column("key_reference", sa.String(length=256), nullable=False),
        sa.Column("key_version", sa.String(length=64), nullable=True),
        sa.Column("aad_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default=sa.text("'active'")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("hard_delete_after", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_accessed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("access_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deletion_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_async_byok_escrow_user_id", "async_byok_escrow", ["user_id"])
    op.create_index("ix_async_byok_escrow_purpose_id", "async_byok_escrow", ["purpose_id"])
    op.create_index("ix_async_byok_escrow_scope_key", "async_byok_escrow", ["scope_key"])
    op.create_index("ix_async_byok_escrow_status", "async_byok_escrow", ["status"])
    op.create_index("ix_async_byok_escrow_expires_at", "async_byok_escrow", ["expires_at"])


def downgrade() -> None:
    op.drop_index("ix_async_byok_escrow_expires_at", table_name="async_byok_escrow")
    op.drop_index("ix_async_byok_escrow_status", table_name="async_byok_escrow")
    op.drop_index("ix_async_byok_escrow_scope_key", table_name="async_byok_escrow")
    op.drop_index("ix_async_byok_escrow_purpose_id", table_name="async_byok_escrow")
    op.drop_index("ix_async_byok_escrow_user_id", table_name="async_byok_escrow")
    op.drop_table("async_byok_escrow")
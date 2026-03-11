"""Add alpha_access_request table.

Revision ID: 015_alpha_access_request
Revises: 014_fix_metering_defaults
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "015_alpha_access_request"
down_revision = "014_fix_metering_defaults"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "alpha_access_request",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(512), nullable=False),
        sa.Column("display_name", sa.String(256), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("invite_token", sa.String(128), nullable=True),
        sa.Column("invite_used", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("promo_code_used", sa.String(128), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
    )
    op.create_index("ix_alpha_access_request_email", "alpha_access_request", ["email"], unique=True)
    op.create_index("ix_alpha_access_request_status", "alpha_access_request", ["status"])
    op.create_index("ix_alpha_access_request_invite_token", "alpha_access_request", ["invite_token"], unique=True)


def downgrade() -> None:
    op.drop_table("alpha_access_request")

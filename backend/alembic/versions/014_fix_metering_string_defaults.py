"""Fix quoted string defaults in metering tables.

Revision ID: 014_fix_metering_string_defaults
Revises: 013_credit_model_metering
Create Date: 2026-03-11
"""

from alembic import op
import sqlalchemy as sa


revision = "014_fix_metering_defaults"
down_revision = "013_credit_model_metering"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE task_model_assignment
        SET rollout_state = 'active'
        WHERE rollout_state = '''active'''
        """
    )
    op.execute(
        """
        UPDATE billing_operation
        SET status = 'pending'
        WHERE status = '''pending'''
        """
    )
    op.execute(
        """
        UPDATE billing_usage_line
        SET status = 'recorded'
        WHERE status = '''recorded'''
        """
    )
    op.execute(
        """
        UPDATE model_task_health
        SET status = 'healthy'
        WHERE status = '''healthy'''
        """
    )

    op.alter_column(
        "task_model_assignment",
        "rollout_state",
        existing_type=sa.String(length=64),
        server_default=sa.text("'active'"),
    )
    op.alter_column(
        "billing_operation",
        "status",
        existing_type=sa.String(length=32),
        server_default=sa.text("'pending'"),
    )
    op.alter_column(
        "billing_usage_line",
        "status",
        existing_type=sa.String(length=32),
        server_default=sa.text("'recorded'"),
    )
    op.alter_column(
        "model_task_health",
        "status",
        existing_type=sa.String(length=32),
        server_default=sa.text("'healthy'"),
    )


def downgrade() -> None:
    op.alter_column(
        "model_task_health",
        "status",
        existing_type=sa.String(length=32),
        server_default="'healthy'",
    )
    op.alter_column(
        "billing_usage_line",
        "status",
        existing_type=sa.String(length=32),
        server_default="'recorded'",
    )
    op.alter_column(
        "billing_operation",
        "status",
        existing_type=sa.String(length=32),
        server_default="'pending'",
    )
    op.alter_column(
        "task_model_assignment",
        "rollout_state",
        existing_type=sa.String(length=64),
        server_default="'active'",
    )

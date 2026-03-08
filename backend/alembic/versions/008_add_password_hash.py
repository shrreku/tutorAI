"""add password_hash to user_profile

Revision ID: 008_add_password_hash
Revises: 007_notebook_domain
Create Date: 2026-03-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "008_add_password_hash"
down_revision = "007_notebook_domain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("user_profile")}
    if "password_hash" not in existing_columns:
        op.add_column(
            "user_profile",
            sa.Column("password_hash", sa.String(length=256), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("user_profile")}
    if "password_hash" in existing_columns:
        op.drop_column("user_profile", "password_hash")

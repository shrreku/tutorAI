from alembic import op
import sqlalchemy as sa


revision = "020_llamaparse_page_allowance"
down_revision = "019_embedding_dimension_1536"
branch_labels = None
depends_on = None


DEFAULT_PAGE_ALLOWANCE = 800


def upgrade() -> None:
    op.add_column(
        "user_profile",
        sa.Column(
            "parse_page_limit",
            sa.Integer(),
            nullable=False,
            server_default=str(DEFAULT_PAGE_ALLOWANCE),
        ),
    )
    op.add_column(
        "user_profile",
        sa.Column(
            "parse_page_used",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "user_profile",
        sa.Column(
            "parse_page_reserved",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.execute(
        f"UPDATE user_profile SET parse_page_limit = {DEFAULT_PAGE_ALLOWANCE} WHERE parse_page_limit IS NULL OR parse_page_limit <= 0"
    )
    op.execute(
        "UPDATE user_profile SET parse_page_used = 0 WHERE parse_page_used IS NULL"
    )
    op.execute(
        "UPDATE user_profile SET parse_page_reserved = 0 WHERE parse_page_reserved IS NULL"
    )
    op.alter_column("user_profile", "parse_page_limit", server_default=None)
    op.alter_column("user_profile", "parse_page_used", server_default=None)
    op.alter_column("user_profile", "parse_page_reserved", server_default=None)


def downgrade() -> None:
    op.drop_column("user_profile", "parse_page_reserved")
    op.drop_column("user_profile", "parse_page_used")
    op.drop_column("user_profile", "parse_page_limit")

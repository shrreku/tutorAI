from typing import Sequence, Union

from alembic import op

revision: str = "019_embedding_dimension_1536"
down_revision: Union[str, None] = "018_subchunk_meta"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunk_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_sub_chunk_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_tutor_turn_state_embedding_hnsw")

    op.execute(
        "UPDATE chunk SET embedding = NULL, embedding_model_id = NULL WHERE embedding IS NOT NULL"
    )
    op.execute(
        "UPDATE sub_chunk SET embedding = NULL, embedding_model_id = NULL WHERE embedding IS NOT NULL"
    )
    op.execute(
        "UPDATE tutor_turn SET rl_state_embedding = NULL WHERE rl_state_embedding IS NOT NULL"
    )
    op.execute(
        "UPDATE tutor_turn SET rl_action_embedding = NULL WHERE rl_action_embedding IS NOT NULL"
    )

    op.execute("ALTER TABLE chunk ALTER COLUMN embedding TYPE vector(1536)")
    op.execute("ALTER TABLE sub_chunk ALTER COLUMN embedding TYPE vector(1536)")
    op.execute("ALTER TABLE tutor_turn ALTER COLUMN rl_state_embedding TYPE vector(1536)")
    op.execute("ALTER TABLE tutor_turn ALTER COLUMN rl_action_embedding TYPE vector(1536)")

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunk_embedding_hnsw ON chunk USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sub_chunk_embedding_hnsw ON sub_chunk USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tutor_turn_state_embedding_hnsw ON tutor_turn USING hnsw (rl_state_embedding vector_cosine_ops)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunk_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_sub_chunk_embedding_hnsw")
    op.execute("DROP INDEX IF EXISTS ix_tutor_turn_state_embedding_hnsw")

    op.execute(
        "UPDATE chunk SET embedding = NULL, embedding_model_id = NULL WHERE embedding IS NOT NULL"
    )
    op.execute(
        "UPDATE sub_chunk SET embedding = NULL, embedding_model_id = NULL WHERE embedding IS NOT NULL"
    )
    op.execute(
        "UPDATE tutor_turn SET rl_state_embedding = NULL WHERE rl_state_embedding IS NOT NULL"
    )
    op.execute(
        "UPDATE tutor_turn SET rl_action_embedding = NULL WHERE rl_action_embedding IS NOT NULL"
    )

    op.execute("ALTER TABLE chunk ALTER COLUMN embedding TYPE vector(384)")
    op.execute("ALTER TABLE sub_chunk ALTER COLUMN embedding TYPE vector(384)")
    op.execute("ALTER TABLE tutor_turn ALTER COLUMN rl_state_embedding TYPE vector(384)")
    op.execute("ALTER TABLE tutor_turn ALTER COLUMN rl_action_embedding TYPE vector(384)")

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_chunk_embedding_hnsw ON chunk USING hnsw (embedding vector_cosine_ops)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_tutor_turn_state_embedding_hnsw ON tutor_turn USING hnsw (rl_state_embedding vector_cosine_ops)"
    )

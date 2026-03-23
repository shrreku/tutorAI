"""Sub-chunk model for fine-grained retrieval.

Parent chunks (~1200 tokens) are kept for LLM enrichment context.
Sub-chunks (~512 tokens) are created for embedding and retrieval.
When a sub-chunk matches, the parent chunk is used for tutor context
while the sub-chunk metadata powers citations.
"""

import uuid
from typing import Optional, TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text, Integer, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.chunk import Chunk


class SubChunk(Base, UUIDMixin, TimestampMixin):
    """A ~512-token segment of a parent chunk, optimized for embedding retrieval."""

    __tablename__ = "sub_chunk"

    parent_chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunk.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resource.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sub_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    page_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    enrichment_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1536), nullable=True)
    embedding_model_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )

    # Relationships
    parent_chunk: Mapped["Chunk"] = relationship("Chunk", backref="sub_chunks")

    __table_args__ = (
        Index("ix_sub_chunk_parent_sub", "parent_chunk_id", "sub_index"),
        Index("ix_sub_chunk_resource", "resource_id"),
    )

import uuid
from typing import Optional, TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import String, Text, Integer, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.resource import Resource


class Chunk(Base, UUIDMixin, TimestampMixin):
    """A semantically coherent text segment from a resource."""

    __tablename__ = "chunk"

    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resource.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    section_heading: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_start: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    page_end: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pedagogy_role: Mapped[Optional[str]] = mapped_column(
        String(64),
        nullable=True,
    )
    difficulty: Mapped[Optional[str]] = mapped_column(
        String(32),
        nullable=True,
    )
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1536), nullable=True)
    enrichment_metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    embedding_model_id: Mapped[Optional[str]] = mapped_column(
        String(128), nullable=True
    )

    # Relationships
    resource: Mapped["Resource"] = relationship("Resource", back_populates="chunks")

    __table_args__ = (
        UniqueConstraint("resource_id", "chunk_index", name="uq_chunk_resource_index"),
        Index("ix_chunk_resource_chunk_index", "resource_id", "chunk_index"),
    )


class ChunkConcept(Base):
    """Direct links between chunks and concept IDs."""

    __tablename__ = "chunk_concept"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunk.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    concept_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="mentions",
    )

    __table_args__ = (
        Index("ix_chunk_concept_chunk_concept", "chunk_id", "concept_id"),
    )


class Formula(Base, UUIDMixin, TimestampMixin):
    """Extracted formulas/equations from resources."""

    __tablename__ = "formula"

    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resource.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    expression_plain: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    variables: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    concept_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    source_chunk_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunk.id", ondelete="SET NULL"),
        nullable=True,
    )

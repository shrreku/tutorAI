"""ProcessingBatch – tracks phased ingestion batches for progressive readiness.

Each batch represents a section-aligned slice of a resource that progresses
through ontology extraction → chunk enrichment → KB merge independently.
"""

import uuid
from datetime import datetime
from typing import Optional, List

from sqlalchemy import String, Text, Integer, DateTime, func, ForeignKey
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TimestampMixin


class ProcessingBatch(Base, UUIDMixin, TimestampMixin):
    """One section-aligned processing slice of a resource."""

    __tablename__ = "processing_batch"

    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resource.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    batch_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    # Section/chunk boundaries
    chunk_index_start: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    chunk_index_end: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    section_headings: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    chunk_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Stage tracking
    ontology_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    enrichment_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    kb_merge_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )
    graph_merge_status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending"
    )

    # Readiness flags
    is_retrieval_ready: Mapped[bool] = mapped_column(default=False, nullable=False)
    is_study_ready: Mapped[bool] = mapped_column(default=False, nullable=False)

    # Results
    concepts_admitted: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    graph_edges_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ontology_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamps for stage completion
    ontology_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    enrichment_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    kb_merge_completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

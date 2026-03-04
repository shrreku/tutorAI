import uuid
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Text, Integer, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey

from app.models.base import Base, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.chunk import Chunk
    from app.models.knowledge_base import (
        ResourceConceptStats,
        ResourceConceptEvidence,
        ResourceConceptGraph,
        ResourceBundle,
        ResourceTopicBundle,
        ResourceTopic,
        ResourceLearningObjective,
        ResourcePrereqHint,
    )


class Resource(Base, UUIDMixin, TimestampMixin):
    """Represents one ingested document/resource."""
    __tablename__ = "resource"

    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    owner_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profile.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    topic: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="processing",
    )
    file_path_or_uri: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    uploaded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    processed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    pipeline_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    chunks: Mapped[List["Chunk"]] = relationship(
        "Chunk",
        back_populates="resource",
        cascade="all, delete-orphan",
    )
    concept_stats: Mapped[List["ResourceConceptStats"]] = relationship(
        "ResourceConceptStats",
        back_populates="resource",
        cascade="all, delete-orphan",
    )
    concept_evidence: Mapped[List["ResourceConceptEvidence"]] = relationship(
        "ResourceConceptEvidence",
        back_populates="resource",
        cascade="all, delete-orphan",
    )
    concept_graph: Mapped[List["ResourceConceptGraph"]] = relationship(
        "ResourceConceptGraph",
        back_populates="resource",
        cascade="all, delete-orphan",
    )
    bundles: Mapped[List["ResourceBundle"]] = relationship(
        "ResourceBundle",
        back_populates="resource",
        cascade="all, delete-orphan",
    )
    topic_bundles: Mapped[List["ResourceTopicBundle"]] = relationship(
        "ResourceTopicBundle",
        back_populates="resource",
        cascade="all, delete-orphan",
    )
    topics: Mapped[List["ResourceTopic"]] = relationship(
        "ResourceTopic",
        back_populates="resource",
        cascade="all, delete-orphan",
    )
    learning_objectives: Mapped[List["ResourceLearningObjective"]] = relationship(
        "ResourceLearningObjective",
        back_populates="resource",
        cascade="all, delete-orphan",
    )
    prereq_hints: Mapped[List["ResourcePrereqHint"]] = relationship(
        "ResourcePrereqHint",
        back_populates="resource",
        cascade="all, delete-orphan",
    )

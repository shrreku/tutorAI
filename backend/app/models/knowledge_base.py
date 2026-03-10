import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Text, Integer, Float, ForeignKey, Index, UniqueConstraint, func, DateTime, text
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.resource import Resource


class ResourceConceptStats(Base):
    """Aggregate statistics per concept within a resource with ontological metadata."""
    __tablename__ = "resource_concept_stats"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resource.id", ondelete="CASCADE"),
        nullable=False,
    )
    concept_id: Mapped[str] = mapped_column(String(256), nullable=False)
    teach_count: Mapped[int] = mapped_column(Integer, default=0)
    mention_count: Mapped[int] = mapped_column(Integer, default=0)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    position_mean: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    position_std: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_quality: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_types: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    # Ontological metadata
    concept_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    bloom_level: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    importance_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Proportional distributions (JSONB)
    type_distribution: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    bloom_distribution: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    difficulty_distribution: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    pedagogy_distribution: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # Topological ordering for prerequisite DAG
    topo_order: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    resource: Mapped["Resource"] = relationship("Resource", back_populates="concept_stats")

    __table_args__ = (
        UniqueConstraint("resource_id", "concept_id", name="uq_resource_concept_stats"),
        Index("ix_resource_concept_stats_resource", "resource_id"),
        Index("ix_resource_concept_stats_concept", "concept_id"),
    )


class ResourceConceptEvidence(Base):
    """Weighted links between concepts and chunks."""
    __tablename__ = "resource_concept_evidence"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resource.id", ondelete="CASCADE"),
        nullable=False,
    )
    concept_id: Mapped[str] = mapped_column(String(256), nullable=False)
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chunk.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(String(32), default="mentions")
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    position_index: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    resource: Mapped["Resource"] = relationship("Resource", back_populates="concept_evidence")

    __table_args__ = (
        Index("ix_resource_concept_evidence_resource_concept", "resource_id", "concept_id"),
        Index("ix_resource_concept_evidence_resource_chunk", "resource_id", "chunk_id"),
    )


class ResourceConceptGraph(Base):
    """Typed semantic edges between concepts within a resource."""
    __tablename__ = "resource_concept_graph"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resource.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_concept_id: Mapped[str] = mapped_column(String(256), nullable=False)
    target_concept_id: Mapped[str] = mapped_column(String(256), nullable=False)
    # Relationship typing
    relation_type: Mapped[str] = mapped_column(
        String(32), 
        default="RELATED_TO",
        nullable=False,
    )
    assoc_weight: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    dir_forward: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    dir_backward: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Source tracking
    source: Mapped[str] = mapped_column(
        String(32),
        default="cooccurrence",
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    resource: Mapped["Resource"] = relationship("Resource", back_populates="concept_graph")

    __table_args__ = (
        Index("ix_resource_concept_graph_source", "resource_id", "source_concept_id"),
        Index("ix_resource_concept_graph_target", "resource_id", "target_concept_id"),
        Index("ix_resource_concept_graph_relation", "resource_id", "relation_type"),
    )


class ResourceBundle(Base):
    """Cached per-concept working set used by retrieval and orchestration."""
    __tablename__ = "resource_bundle"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resource.id", ondelete="CASCADE"),
        nullable=False,
    )
    primary_concept_id: Mapped[str] = mapped_column(String(256), nullable=False)
    support_concepts: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    prereq_hints: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    evidence_prototypes: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    resource: Mapped["Resource"] = relationship("Resource", back_populates="bundles")

    __table_args__ = (
        UniqueConstraint("resource_id", "primary_concept_id", name="uq_resource_bundle"),
        Index("ix_resource_bundle_resource", "resource_id"),
    )


class ResourceTopicBundle(Base):
    """Higher-level groupings used by curriculum/objective generation."""
    __tablename__ = "resource_topic_bundle"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resource.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_id: Mapped[str] = mapped_column(String(256), nullable=False)
    topic_name: Mapped[str] = mapped_column(String(512), nullable=False)
    primary_concepts: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    support_concepts: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    prereq_topic_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    representative_chunk_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )

    resource: Mapped["Resource"] = relationship("Resource", back_populates="topic_bundles")

    __table_args__ = (
        UniqueConstraint("resource_id", "topic_id", name="uq_resource_topic_bundle"),
        Index("ix_resource_topic_bundle_resource", "resource_id"),
    )


class ResourceTopic(Base):
    """Persisted topic strings derived from extraction/enrichment."""
    __tablename__ = "resource_topic"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resource.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_string: Mapped[str] = mapped_column(String(512), nullable=False)

    resource: Mapped["Resource"] = relationship("Resource", back_populates="topics")

    __table_args__ = (
        Index("ix_resource_topic_resource", "resource_id"),
    )


class ResourceLearningObjective(Base):
    """Persisted learning objective strings."""
    __tablename__ = "resource_learning_objective"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resource.id", ondelete="CASCADE"),
        nullable=False,
    )
    objective_text: Mapped[str] = mapped_column(Text, nullable=False)
    specificity: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    resource: Mapped["Resource"] = relationship("Resource", back_populates="learning_objectives")

    __table_args__ = (
        Index("ix_resource_learning_objective_resource", "resource_id"),
    )


class ResourcePrereqHint(Base):
    """Soft prerequisite hints derived from chunk enrichment."""
    __tablename__ = "resource_prereq_hint"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("uuid_generate_v4()")
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resource.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_concept_id: Mapped[str] = mapped_column(String(256), nullable=False)
    target_concept_id: Mapped[str] = mapped_column(String(256), nullable=False)
    support_count: Mapped[int] = mapped_column(Integer, default=0)
    sources: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    resource: Mapped["Resource"] = relationship("Resource", back_populates="prereq_hints")

    __table_args__ = (
        Index("ix_resource_prereq_hint_resource", "resource_id"),
    )

import uuid
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Text, Integer, DateTime, func
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey

from app.models.base import Base, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.chunk import Chunk
    from app.models.resource_artifact import ResourceArtifactState
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


def default_resource_capabilities() -> dict:
    return {
        "study_ready": False,
        "vector_search_ready": False,
        "basic_tutoring_ready": False,
        "can_search": False,
        "can_answer_doubts": False,
        "can_generate_basic_practice": False,
        "can_tutor_basic": False,
        "can_start_learn_session": False,
        "can_start_practice_session": False,
        "can_start_revision_session": False,
        "resource_profile_ready": False,
        "has_resource_profile": False,
        "topic_prepare_ready": False,
        "concepts_ready": False,
        "has_concepts": False,
        "has_topic_bundles": False,
        "has_prereq_graph": False,
        "graph_ready": False,
        "has_curriculum_artifacts": False,
        "curriculum_ready": False,
        "is_graph_synced": False,
        "neo4j_synced": False,
    }


def study_ready_capabilities(existing: Optional[dict] = None, *, has_concepts: bool = True) -> dict:
    capabilities = default_resource_capabilities()
    if existing:
        capabilities.update(existing)
    capabilities.update(
        {
            "vector_search_ready": True,
            "can_search": True,
        }
    )
    capabilities.update(
        {
            "study_ready": has_concepts,
            "basic_tutoring_ready": has_concepts,
            "can_answer_doubts": has_concepts,
            "can_generate_basic_practice": has_concepts,
            "can_tutor_basic": has_concepts,
            "concepts_ready": has_concepts,
            "has_concepts": has_concepts,
        }
    )
    return capabilities


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
    study_ready_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    tutoring_ready_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    curriculum_ready_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    graph_ready_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    pipeline_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    processing_profile: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, default="core_only")
    capabilities_json: Mapped[Optional[dict]] = mapped_column(
        JSONB,
        nullable=True,
        default=default_resource_capabilities,
    )
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
    artifact_states: Mapped[List["ResourceArtifactState"]] = relationship(
        "ResourceArtifactState",
        back_populates="resource",
        cascade="all, delete-orphan",
    )

import uuid
from datetime import datetime
from typing import Optional, List

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    String,
    Text,
    Integer,
    Float,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    DateTime,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TimestampMixin


class UserProfile(Base, UUIDMixin, TimestampMixin):
    """User traits and global mastery."""

    __tablename__ = "user_profile"

    external_id: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True, unique=True
    )
    display_name: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    password_hash: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    global_mastery: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    preferences: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    model_preferences: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    learning_preferences: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    consent_personalization: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, server_default="true",
        doc="User opt-in for personalization data collection (RL research)",
    )
    parse_page_limit: Mapped[int] = mapped_column(
        Integer, nullable=False, default=800, server_default="800"
    )
    parse_page_used: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    parse_page_reserved: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )

    # Relationships
    sessions: Mapped[List["UserSession"]] = relationship(
        "UserSession",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class UserSession(Base, UUIDMixin, TimestampMixin):
    """Session state for tutoring."""

    __tablename__ = "user_session"

    user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profile.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resource.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    consent_training: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        doc="Explicit user opt-in for training-data usage",
    )
    plan_state: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    mastery: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    token_usage: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    personalization_snapshot: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True,
        doc="Effective personalization at session start (user+notebook+session merged). Used for RL reward attribution.",
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    user: Mapped["UserProfile"] = relationship("UserProfile", back_populates="sessions")
    turns: Mapped[List["TutorTurn"]] = relationship(
        "TutorTurn",
        back_populates="session",
        cascade="all, delete-orphan",
    )


class TutorTurn(Base, UUIDMixin, TimestampMixin):
    """A durable turn log suitable for offline training/evaluation."""

    __tablename__ = "tutor_turn"

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_session.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    turn_index: Mapped[int] = mapped_column(Integer, nullable=False)

    # Student input
    student_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Tutor output
    tutor_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    tutor_question: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Curriculum context
    current_step_index: Mapped[Optional[int]] = mapped_column(
        "curriculum_phase_index",
        Integer,
        nullable=True,
    )
    current_step: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    target_concepts: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    pedagogical_action: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    progression_decision: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Full agent outputs
    policy_output: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    evaluator_output: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    retrieved_chunks: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Mastery tracking
    mastery_before: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    mastery_after: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # RL fields
    rl_reward: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rl_state_embedding: Mapped[Optional[list]] = mapped_column(
        Vector(1536), nullable=True
    )
    rl_action_embedding: Mapped[Optional[list]] = mapped_column(
        Vector(1536), nullable=True
    )

    # Performance tracking
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    session: Mapped["UserSession"] = relationship("UserSession", back_populates="turns")

    __table_args__ = (
        UniqueConstraint(
            "session_id", "turn_index", name="uq_tutor_turn_session_index"
        ),
    )

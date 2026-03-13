import uuid
from datetime import datetime
from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import (
    String,
    Text,
    Boolean,
    ForeignKey,
    UniqueConstraint,
    DateTime,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.resource import Resource
    from app.models.session import UserSession


class Notebook(Base, UUIDMixin, TimestampMixin):
    """Primary notebook/course workspace for a user."""

    __tablename__ = "notebook"

    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profile.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    goal: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    target_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")
    settings_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    resources: Mapped[List["NotebookResource"]] = relationship(
        "NotebookResource",
        back_populates="notebook",
        cascade="all, delete-orphan",
    )
    sessions: Mapped[List["NotebookSession"]] = relationship(
        "NotebookSession",
        back_populates="notebook",
        cascade="all, delete-orphan",
    )
    progress: Mapped[Optional["NotebookProgress"]] = relationship(
        "NotebookProgress",
        back_populates="notebook",
        cascade="all, delete-orphan",
        uselist=False,
    )
    artifacts: Mapped[List["NotebookArtifact"]] = relationship(
        "NotebookArtifact",
        back_populates="notebook",
        cascade="all, delete-orphan",
    )


class NotebookResource(Base, UUIDMixin, TimestampMixin):
    """Link table between notebooks and resources."""

    __tablename__ = "notebook_resource"

    notebook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notebook.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    resource_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resource.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(
        String(32), nullable=False, default="supplemental"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    notebook: Mapped["Notebook"] = relationship("Notebook", back_populates="resources")
    resource: Mapped["Resource"] = relationship("Resource")

    __table_args__ = (
        UniqueConstraint(
            "notebook_id", "resource_id", name="uq_notebook_resource_pair"
        ),
    )


class NotebookSession(Base, UUIDMixin, TimestampMixin):
    """Notebook context mapping for tutoring sessions."""

    __tablename__ = "notebook_session"

    notebook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notebook.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_session.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mode: Mapped[str] = mapped_column(String(32), nullable=False, default="learn")
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    ended_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    notebook: Mapped["Notebook"] = relationship("Notebook", back_populates="sessions")
    session: Mapped["UserSession"] = relationship("UserSession")

    __table_args__ = (
        UniqueConstraint("notebook_id", "session_id", name="uq_notebook_session_pair"),
    )


class NotebookProgress(Base, UUIDMixin, TimestampMixin):
    """Notebook-level aggregate progress snapshot."""

    __tablename__ = "notebook_progress"

    notebook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notebook.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    mastery_snapshot: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    objective_progress_snapshot: Mapped[Optional[dict]] = mapped_column(
        JSONB, nullable=True
    )
    weak_concepts_snapshot: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    notebook: Mapped["Notebook"] = relationship("Notebook", back_populates="progress")


class NotebookArtifact(Base, UUIDMixin, TimestampMixin):
    """Generated notebook artifacts (notes, quizzes, flashcards, revision plans)."""

    __tablename__ = "notebook_artifact"

    notebook_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notebook.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_session_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    source_resource_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)

    notebook: Mapped["Notebook"] = relationship("Notebook", back_populates="artifacts")

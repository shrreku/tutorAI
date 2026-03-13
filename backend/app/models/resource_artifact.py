import uuid
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.models.notebook import Notebook
    from app.models.resource import Resource


class ResourceArtifactState(Base, UUIDMixin, TimestampMixin):
    """Internal prepared artifact cache for resource/notebook understanding."""

    __tablename__ = "resource_artifact_state"

    resource_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("resource.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    notebook_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("notebook.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(256), nullable=False)
    artifact_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="ready")
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="1.0")
    payload_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    source_chunk_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True)
    content_hash: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    resource: Mapped[Optional["Resource"]] = relationship(
        "Resource", back_populates="artifact_states"
    )
    notebook: Mapped[Optional["Notebook"]] = relationship("Notebook")

    __table_args__ = (
        Index(
            "ix_resource_artifact_scope_kind",
            "resource_id",
            "notebook_id",
            "scope_type",
            "scope_key",
            "artifact_kind",
        ),
    )

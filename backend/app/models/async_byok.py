import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, LargeBinary, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, UUIDMixin, TimestampMixin


class AsyncByokEscrow(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "async_byok_escrow"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profile.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purpose_type: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose_id: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    scope_type: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_key: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    provider_name: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ciphertext_blob: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    wrapped_dek: Mapped[str] = mapped_column(Text, nullable=False)
    key_backend: Mapped[str] = mapped_column(String(32), nullable=False)
    key_reference: Mapped[str] = mapped_column(String(256), nullable=False)
    key_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    aad_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    hard_delete_after: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_accessed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deletion_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
"""Credits domain models — ledger, accounts, and grants.

Design inspired by GitHub Copilot / Cursor / Windsurf usage-based billing.
All balance changes go through the append-only ``credit_ledger_entry`` table
so that the balance can always be exactly recomputed from the ledger.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, UUIDMixin, TimestampMixin


class CreditAccount(Base, UUIDMixin, TimestampMixin):
    """One account per user — tracks cached balance and plan tier."""

    __tablename__ = "credit_account"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profile.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    balance: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    lifetime_granted: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    lifetime_used: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    plan_tier: Mapped[str] = mapped_column(String(64), nullable=False, default="free_research")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    grants: Mapped[list["CreditGrant"]] = relationship(
        "CreditGrant", back_populates="account", cascade="all, delete-orphan"
    )
    ledger_entries: Mapped[list["CreditLedgerEntry"]] = relationship(
        "CreditLedgerEntry", back_populates="account", cascade="all, delete-orphan"
    )


class CreditGrant(Base, UUIDMixin, TimestampMixin):
    """A grant of credits (monthly allocation, admin top-up, promo, etc.)."""

    __tablename__ = "credit_grant"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("credit_account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    remaining: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source: Mapped[str] = mapped_column(
        String(64), nullable=False, default="monthly_grant"
    )  # monthly_grant | signup_grant | admin_topup | promo | refund
    memo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    account: Mapped["CreditAccount"] = relationship(
        "CreditAccount", back_populates="grants"
    )


class CreditLedgerEntry(Base, UUIDMixin, TimestampMixin):
    """Append-only ledger entry for every credit mutation.

    ``entry_type`` values:
    - grant       : credits added (positive delta)
    - reserve     : credits tentatively held for an in-progress operation
    - debit       : credits finalized after operation completes
    - release     : reserved credits returned (operation cancelled / cheaper than reserved)
    - refund      : manual admin refund
    - expire      : grant expiration sweep
    """

    __tablename__ = "credit_ledger_entry"

    account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("credit_account.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entry_type: Mapped[str] = mapped_column(
        String(32), nullable=False
    )  # grant | reserve | debit | release | refund | expire
    delta: Mapped[int] = mapped_column(
        BigInteger, nullable=False
    )  # positive = add, negative = deduct
    balance_after: Mapped[int] = mapped_column(BigInteger, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True, unique=True
    )
    reference_type: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True
    )  # turn | ingestion | grant | admin
    reference_id: Mapped[Optional[str]] = mapped_column(
        String(256), nullable=True
    )  # turn_id, job_id, grant_id, etc.
    metadata_: Mapped[Optional[dict]] = mapped_column(
        "metadata", JSONB, nullable=True
    )

    # Relationships
    account: Mapped["CreditAccount"] = relationship(
        "CreditAccount", back_populates="ledger_entries"
    )

    __table_args__ = (
        Index("ix_credit_ledger_created", "account_id", "created_at"),
    )


class ModelMultiplier(Base, UUIDMixin, TimestampMixin):
    """Per-model credit multiplier table for metering."""

    __tablename__ = "model_multiplier"

    model_id: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    input_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    output_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.5)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

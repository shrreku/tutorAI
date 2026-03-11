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


# ---------------------------------------------------------------------------
# CM-001: Hosted model pricing registry
# ---------------------------------------------------------------------------

class ModelPricing(Base, UUIDMixin, TimestampMixin):
    """Source of truth for hosted model pricing and product metadata."""

    __tablename__ = "model_pricing"

    model_id: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    provider_name: Mapped[str] = mapped_column(String(128), nullable=False)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    model_class: Mapped[str] = mapped_column(String(64), nullable=False)  # economy | standard | premium_small
    input_usd_per_million: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    output_usd_per_million: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cache_write_usd_per_million: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    cache_read_usd_per_million: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    search_usd_per_unit: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    is_user_selectable: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    supports_structured_output: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_long_context: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    supports_byok: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    deprecated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# CM-002: Task-model assignment registry
# ---------------------------------------------------------------------------

class TaskModelAssignment(Base, UUIDMixin, TimestampMixin):
    """Explicit task → model mapping with fallback and override support."""

    __tablename__ = "task_model_assignment"

    task_type: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    default_model_id: Mapped[str] = mapped_column(String(256), nullable=False)
    fallback_model_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    allowed_model_ids: Mapped[Optional[list]] = mapped_column(JSONB, nullable=True, default=list)
    user_override_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rollout_state: Mapped[str] = mapped_column(String(64), nullable=False, default="active")  # active | beta | disabled
    beta_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


# ---------------------------------------------------------------------------
# CM-003: Billing operation and usage-line tables
# ---------------------------------------------------------------------------

class BillingOperation(Base, UUIDMixin, TimestampMixin):
    """Top-level metered operation (one per billed action)."""

    __tablename__ = "billing_operation"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("user_profile.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    operation_type: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True,
    )  # ingestion_upload | notebook_session_launch | tutor_turn | artifact_generate
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending",
    )  # pending | reserved | finalized | failed | released
    resource_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    artifact_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    selected_model_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    routed_model_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    reroute_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    estimate_credits_low: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    estimate_credits_high: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    reserved_credits: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    final_credits: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    final_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSONB, nullable=True)

    # Relationships
    usage_lines: Mapped[list["BillingUsageLine"]] = relationship(
        "BillingUsageLine", back_populates="operation", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_billing_op_user_created", "user_id", "created_at"),
        Index("ix_billing_op_type_status", "operation_type", "status"),
    )


class BillingUsageLine(Base, UUIDMixin, TimestampMixin):
    """Individual usage line within an operation (one per model call)."""

    __tablename__ = "billing_usage_line"

    operation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("billing_operation.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_type: Mapped[str] = mapped_column(String(128), nullable=False)
    model_id: Mapped[str] = mapped_column(String(256), nullable=False)
    provider_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cache_write_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    cache_read_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    tool_units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_usd: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="recorded")  # recorded | error

    # Relationships
    operation: Mapped["BillingOperation"] = relationship(
        "BillingOperation", back_populates="usage_lines"
    )


# ---------------------------------------------------------------------------
# CM-010: Model-task health registry
# ---------------------------------------------------------------------------

class ModelTaskHealth(Base, UUIDMixin, TimestampMixin):
    """Per model-task health tracking for cooldown and routing."""

    __tablename__ = "model_task_health"

    model_id: Mapped[str] = mapped_column(String(256), nullable=False)
    task_type: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="healthy",
    )  # healthy | degraded | disabled | manual_only
    consecutive_errors: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rolling_error_rate: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cooldown_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_success_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_code: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    manual_override_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    __table_args__ = (
        UniqueConstraint("model_id", "task_type", name="uq_model_task_health"),
        Index("ix_model_task_health_lookup", "model_id", "task_type"),
    )

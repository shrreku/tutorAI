"""Metering repository — operations, usage lines, pricing lookups.

Handles the new operation-based billing tables introduced by CM-003/CM-004.
"""

import logging
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.credits import (
    BillingOperation,
    BillingUsageLine,
    ModelPricing,
    TaskModelAssignment,
    ModelTaskHealth,
)

logger = logging.getLogger(__name__)


class MeteringRepository:
    """Manages billing operations, usage lines, and pricing lookups."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Model pricing
    # ------------------------------------------------------------------

    async def get_model_pricing(self, model_id: str) -> Optional[ModelPricing]:
        result = await self.db.execute(
            select(ModelPricing).where(
                ModelPricing.model_id == model_id,
                ModelPricing.is_active,
            )
        )
        return result.scalar_one_or_none()

    async def list_active_models(self) -> list[ModelPricing]:
        result = await self.db.execute(
            select(ModelPricing)
            .where(ModelPricing.is_active)
            .order_by(ModelPricing.model_class, ModelPricing.display_name)
        )
        return list(result.scalars().all())

    async def list_user_selectable_models(self) -> list[ModelPricing]:
        result = await self.db.execute(
            select(ModelPricing)
            .where(
                ModelPricing.is_active,
                ModelPricing.is_user_selectable,
            )
            .order_by(ModelPricing.model_class, ModelPricing.display_name)
        )
        return list(result.scalars().all())

    async def update_model_pricing(
        self, model_id: str, **kwargs
    ) -> Optional[ModelPricing]:
        pricing = await self.get_model_pricing(model_id)
        if not pricing:
            return None
        for key, value in kwargs.items():
            if hasattr(pricing, key):
                setattr(pricing, key, value)
        self.db.add(pricing)
        await self.db.flush()
        return pricing

    # ------------------------------------------------------------------
    # Task-model assignments
    # ------------------------------------------------------------------

    async def get_assignment(self, task_type: str) -> Optional[TaskModelAssignment]:
        result = await self.db.execute(
            select(TaskModelAssignment).where(
                TaskModelAssignment.task_type == task_type
            )
        )
        return result.scalar_one_or_none()

    async def list_assignments(self) -> list[TaskModelAssignment]:
        result = await self.db.execute(
            select(TaskModelAssignment).order_by(TaskModelAssignment.task_type)
        )
        return list(result.scalars().all())

    async def update_assignment(
        self, task_type: str, **kwargs
    ) -> Optional[TaskModelAssignment]:
        assignment = await self.get_assignment(task_type)
        if not assignment:
            return None
        for key, value in kwargs.items():
            if hasattr(assignment, key):
                setattr(assignment, key, value)
        self.db.add(assignment)
        await self.db.flush()
        return assignment

    # ------------------------------------------------------------------
    # Billing operations
    # ------------------------------------------------------------------

    async def create_operation(
        self,
        user_id: uuid.UUID,
        operation_type: str,
        *,
        resource_id: Optional[str] = None,
        session_id: Optional[str] = None,
        artifact_id: Optional[str] = None,
        selected_model_id: Optional[str] = None,
        estimate_credits_low: Optional[int] = None,
        estimate_credits_high: Optional[int] = None,
        metadata: Optional[dict] = None,
    ) -> BillingOperation:
        op = BillingOperation(
            user_id=user_id,
            operation_type=operation_type,
            status="pending",
            resource_id=resource_id,
            session_id=session_id,
            artifact_id=artifact_id,
            selected_model_id=selected_model_id,
            estimate_credits_low=estimate_credits_low,
            estimate_credits_high=estimate_credits_high,
            metadata_=metadata,
        )
        self.db.add(op)
        await self.db.flush()
        return op

    async def get_operation(
        self, operation_id: uuid.UUID
    ) -> Optional[BillingOperation]:
        result = await self.db.execute(
            select(BillingOperation).where(BillingOperation.id == operation_id)
        )
        return result.scalar_one_or_none()

    async def update_operation_status(
        self,
        operation_id: uuid.UUID,
        status: str,
        *,
        reserved_credits: Optional[int] = None,
        final_credits: Optional[int] = None,
        final_usd: Optional[float] = None,
        routed_model_id: Optional[str] = None,
        reroute_reason: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> Optional[BillingOperation]:
        op = await self.get_operation(operation_id)
        if not op:
            return None
        op.status = status
        if reserved_credits is not None:
            op.reserved_credits = reserved_credits
        if final_credits is not None:
            op.final_credits = final_credits
        if final_usd is not None:
            op.final_usd = final_usd
        if routed_model_id is not None:
            op.routed_model_id = routed_model_id
        if reroute_reason is not None:
            op.reroute_reason = reroute_reason
        if metadata is not None:
            op.metadata_ = {**(op.metadata_ or {}), **metadata}
        self.db.add(op)
        await self.db.flush()
        return op

    async def list_user_operations(
        self,
        user_id: uuid.UUID,
        limit: int = 50,
        operation_type: Optional[str] = None,
    ) -> list[BillingOperation]:
        query = (
            select(BillingOperation)
            .where(BillingOperation.user_id == user_id)
            .order_by(BillingOperation.created_at.desc())
            .limit(limit)
        )
        if operation_type:
            query = query.where(BillingOperation.operation_type == operation_type)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Usage lines
    # ------------------------------------------------------------------

    async def append_usage_line(
        self,
        operation_id: uuid.UUID,
        task_type: str,
        model_id: str,
        *,
        provider_name: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_write_tokens: int = 0,
        cache_read_tokens: int = 0,
        tool_units: int = 0,
        raw_usd: float = 0.0,
        status: str = "recorded",
    ) -> BillingUsageLine:
        line = BillingUsageLine(
            operation_id=operation_id,
            task_type=task_type,
            model_id=model_id,
            provider_name=provider_name,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_write_tokens=cache_write_tokens,
            cache_read_tokens=cache_read_tokens,
            tool_units=tool_units,
            raw_usd=raw_usd,
            status=status,
        )
        self.db.add(line)
        await self.db.flush()
        return line

    async def get_operation_usage_lines(
        self, operation_id: uuid.UUID
    ) -> list[BillingUsageLine]:
        result = await self.db.execute(
            select(BillingUsageLine)
            .where(BillingUsageLine.operation_id == operation_id)
            .order_by(BillingUsageLine.created_at)
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Model-task health
    # ------------------------------------------------------------------

    async def get_health(
        self, model_id: str, task_type: str
    ) -> Optional[ModelTaskHealth]:
        result = await self.db.execute(
            select(ModelTaskHealth).where(
                ModelTaskHealth.model_id == model_id,
                ModelTaskHealth.task_type == task_type,
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create_health(
        self, model_id: str, task_type: str
    ) -> ModelTaskHealth:
        health = await self.get_health(model_id, task_type)
        if health is None:
            health = ModelTaskHealth(model_id=model_id, task_type=task_type)
            self.db.add(health)
            await self.db.flush()
        return health

    async def list_health(
        self, model_id: Optional[str] = None
    ) -> list[ModelTaskHealth]:
        query = select(ModelTaskHealth).order_by(
            ModelTaskHealth.model_id, ModelTaskHealth.task_type
        )
        if model_id:
            query = query.where(ModelTaskHealth.model_id == model_id)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update_health(
        self,
        model_id: str,
        task_type: str,
        **kwargs,
    ) -> ModelTaskHealth:
        health = await self.get_or_create_health(model_id, task_type)
        for key, value in kwargs.items():
            if hasattr(health, key):
                setattr(health, key, value)
        self.db.add(health)
        await self.db.flush()
        return health

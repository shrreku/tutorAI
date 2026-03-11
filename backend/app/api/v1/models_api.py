"""Admin and user APIs for model pricing, assignments, and health controls.

CM-011: Admin endpoints
CM-012: User model catalog and preference endpoints
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_auth, require_admin
from app.config import settings
from app.db.database import get_db
from app.db.repositories.metering_repo import MeteringRepository
from app.models.session import UserProfile
from app.services.credits.health import ModelHealthService

router = APIRouter(prefix="/models", tags=["models"])
logger = logging.getLogger(__name__)


# ---- Schemas ----

class ModelPricingResponse(BaseModel):
    model_id: str
    provider_name: str
    display_name: str
    model_class: str
    input_usd_per_million: float
    output_usd_per_million: float
    cache_write_usd_per_million: Optional[float] = None
    cache_read_usd_per_million: Optional[float] = None
    is_active: bool
    is_user_selectable: bool
    supports_structured_output: bool
    supports_long_context: bool
    notes: Optional[str] = None


class ModelPricingUpdateRequest(BaseModel):
    input_usd_per_million: Optional[float] = None
    output_usd_per_million: Optional[float] = None
    is_active: Optional[bool] = None
    is_user_selectable: Optional[bool] = None
    notes: Optional[str] = None


class TaskAssignmentResponse(BaseModel):
    task_type: str
    default_model_id: str
    fallback_model_ids: list[str]
    allowed_model_ids: list[str]
    user_override_allowed: bool
    rollout_state: str
    beta_only: bool


class TaskAssignmentUpdateRequest(BaseModel):
    default_model_id: Optional[str] = None
    fallback_model_ids: Optional[list[str]] = None
    allowed_model_ids: Optional[list[str]] = None
    user_override_allowed: Optional[bool] = None
    rollout_state: Optional[str] = None


class ModelTaskHealthResponse(BaseModel):
    model_id: str
    task_type: str
    status: str
    consecutive_errors: int
    rolling_error_rate: float
    cooldown_until: Optional[str] = None
    last_success_at: Optional[str] = None
    last_error_at: Optional[str] = None
    last_error_code: Optional[str] = None
    last_error_summary: Optional[str] = None
    manual_override_reason: Optional[str] = None


class HealthActionRequest(BaseModel):
    model_id: str
    task_type: str
    reason: str = ""


class UserModelPreferencesResponse(BaseModel):
    model_selection_enabled: bool
    preferences: dict


class UserModelPreferencesUpdateRequest(BaseModel):
    tutoring_model_id: Optional[str] = None
    artifact_model_id: Optional[str] = None
    upload_model_id: Optional[str] = None


class TaskModelsResponse(BaseModel):
    task_type: str
    allowed_models: list[ModelPricingResponse]
    default_model_id: str
    user_override_allowed: bool


class OperationResponse(BaseModel):
    id: str
    operation_type: str
    status: str
    selected_model_id: Optional[str] = None
    routed_model_id: Optional[str] = None
    reroute_reason: Optional[str] = None
    estimate_credits_low: Optional[int] = None
    estimate_credits_high: Optional[int] = None
    reserved_credits: int = 0
    final_credits: Optional[int] = None
    final_usd: Optional[float] = None
    created_at: str


class OperationHistoryResponse(BaseModel):
    operations: list[OperationResponse]


# ---- User endpoints (CM-012) ----

@router.get("/catalog", response_model=list[ModelPricingResponse])
async def get_model_catalog(
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Get available model catalog for users."""
    repo = MeteringRepository(db)
    models = await repo.list_user_selectable_models()
    return [
        ModelPricingResponse(
            model_id=m.model_id,
            provider_name=m.provider_name,
            display_name=m.display_name,
            model_class=m.model_class,
            input_usd_per_million=m.input_usd_per_million,
            output_usd_per_million=m.output_usd_per_million,
            cache_write_usd_per_million=m.cache_write_usd_per_million,
            cache_read_usd_per_million=m.cache_read_usd_per_million,
            is_active=m.is_active,
            is_user_selectable=m.is_user_selectable,
            supports_structured_output=m.supports_structured_output,
            supports_long_context=m.supports_long_context,
            notes=m.notes,
        )
        for m in models
    ]


@router.get("/tasks/{task_type}", response_model=TaskModelsResponse)
async def get_task_models(
    task_type: str,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Get allowed models for a specific task."""
    repo = MeteringRepository(db)
    assignment = await repo.get_assignment(task_type)
    if not assignment:
        raise HTTPException(status_code=404, detail=f"Task {task_type} not found")

    allowed_ids = assignment.allowed_model_ids or []
    models = []
    for mid in allowed_ids:
        pricing = await repo.get_model_pricing(mid)
        if pricing and pricing.is_active:
            models.append(ModelPricingResponse(
                model_id=pricing.model_id,
                provider_name=pricing.provider_name,
                display_name=pricing.display_name,
                model_class=pricing.model_class,
                input_usd_per_million=pricing.input_usd_per_million,
                output_usd_per_million=pricing.output_usd_per_million,
                cache_write_usd_per_million=pricing.cache_write_usd_per_million,
                cache_read_usd_per_million=pricing.cache_read_usd_per_million,
                is_active=pricing.is_active,
                is_user_selectable=pricing.is_user_selectable,
                supports_structured_output=pricing.supports_structured_output,
                supports_long_context=pricing.supports_long_context,
                notes=pricing.notes,
            ))

    return TaskModelsResponse(
        task_type=task_type,
        allowed_models=models,
        default_model_id=assignment.default_model_id,
        user_override_allowed=assignment.user_override_allowed,
    )


@router.get("/preferences", response_model=UserModelPreferencesResponse)
async def get_user_preferences(
    user: UserProfile = Depends(require_auth),
):
    """Get current user model preferences."""
    return UserModelPreferencesResponse(
        model_selection_enabled=settings.MODEL_SELECTION_ENABLED,
        preferences=user.model_preferences or {},
    )


@router.put("/preferences", response_model=UserModelPreferencesResponse)
async def update_user_preferences(
    request: UserModelPreferencesUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Update user model preferences."""
    if not settings.MODEL_SELECTION_ENABLED:
        raise HTTPException(status_code=400, detail="Model selection is not enabled")

    prefs = user.model_preferences or {}
    repo = MeteringRepository(db)

    # Validate model IDs
    for field_name, model_id in [
        ("tutoring_model_id", request.tutoring_model_id),
        ("artifact_model_id", request.artifact_model_id),
        ("upload_model_id", request.upload_model_id),
    ]:
        if model_id is not None:
            pricing = await repo.get_model_pricing(model_id)
            if not pricing or not pricing.is_active or not pricing.is_user_selectable:
                raise HTTPException(
                    status_code=400,
                    detail=f"Model '{model_id}' is not available for selection",
                )
            prefs[field_name] = model_id

    user.model_preferences = prefs
    db.add(user)
    await db.commit()

    return UserModelPreferencesResponse(
        model_selection_enabled=settings.MODEL_SELECTION_ENABLED,
        preferences=prefs,
    )


@router.get("/operations", response_model=OperationHistoryResponse)
async def get_operation_history(
    limit: int = Query(default=50, ge=1, le=200),
    operation_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Get user's billing operation history."""
    repo = MeteringRepository(db)
    ops = await repo.list_user_operations(user.id, limit=limit, operation_type=operation_type)
    return OperationHistoryResponse(
        operations=[
            OperationResponse(
                id=str(o.id),
                operation_type=o.operation_type,
                status=o.status,
                selected_model_id=o.selected_model_id,
                routed_model_id=o.routed_model_id,
                reroute_reason=o.reroute_reason,
                estimate_credits_low=o.estimate_credits_low,
                estimate_credits_high=o.estimate_credits_high,
                reserved_credits=o.reserved_credits,
                final_credits=o.final_credits,
                final_usd=o.final_usd,
                created_at=o.created_at.isoformat() if o.created_at else "",
            )
            for o in ops
        ]
    )


# ---- Admin endpoints (CM-011) ----

@router.get("/admin/pricing", response_model=list[ModelPricingResponse])
async def admin_list_pricing(
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_admin),
):
    """Admin: list all model pricing entries."""
    repo = MeteringRepository(db)
    models = await repo.list_active_models()
    return [
        ModelPricingResponse(
            model_id=m.model_id,
            provider_name=m.provider_name,
            display_name=m.display_name,
            model_class=m.model_class,
            input_usd_per_million=m.input_usd_per_million,
            output_usd_per_million=m.output_usd_per_million,
            cache_write_usd_per_million=m.cache_write_usd_per_million,
            cache_read_usd_per_million=m.cache_read_usd_per_million,
            is_active=m.is_active,
            is_user_selectable=m.is_user_selectable,
            supports_structured_output=m.supports_structured_output,
            supports_long_context=m.supports_long_context,
            notes=m.notes,
        )
        for m in models
    ]


@router.patch("/admin/pricing/{model_id:path}", response_model=ModelPricingResponse)
async def admin_update_pricing(
    model_id: str,
    request: ModelPricingUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_admin),
):
    """Admin: update model pricing."""
    repo = MeteringRepository(db)
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    pricing = await repo.update_model_pricing(model_id, **updates)
    if not pricing:
        raise HTTPException(status_code=404, detail=f"Model {model_id} not found")

    await db.commit()
    logger.warning("Admin %s updated pricing for %s: %s", user.external_id, model_id, updates)

    return ModelPricingResponse(
        model_id=pricing.model_id,
        provider_name=pricing.provider_name,
        display_name=pricing.display_name,
        model_class=pricing.model_class,
        input_usd_per_million=pricing.input_usd_per_million,
        output_usd_per_million=pricing.output_usd_per_million,
        cache_write_usd_per_million=pricing.cache_write_usd_per_million,
        cache_read_usd_per_million=pricing.cache_read_usd_per_million,
        is_active=pricing.is_active,
        is_user_selectable=pricing.is_user_selectable,
        supports_structured_output=pricing.supports_structured_output,
        supports_long_context=pricing.supports_long_context,
        notes=pricing.notes,
    )


@router.get("/admin/assignments", response_model=list[TaskAssignmentResponse])
async def admin_list_assignments(
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_admin),
):
    """Admin: list all task-model assignments."""
    repo = MeteringRepository(db)
    assignments = await repo.list_assignments()
    return [
        TaskAssignmentResponse(
            task_type=a.task_type,
            default_model_id=a.default_model_id,
            fallback_model_ids=a.fallback_model_ids or [],
            allowed_model_ids=a.allowed_model_ids or [],
            user_override_allowed=a.user_override_allowed,
            rollout_state=a.rollout_state,
            beta_only=a.beta_only,
        )
        for a in assignments
    ]


@router.patch("/admin/assignments/{task_type}", response_model=TaskAssignmentResponse)
async def admin_update_assignment(
    task_type: str,
    request: TaskAssignmentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_admin),
):
    """Admin: update a task-model assignment."""
    repo = MeteringRepository(db)
    updates = {k: v for k, v in request.model_dump().items() if v is not None}
    assignment = await repo.update_assignment(task_type, **updates)
    if not assignment:
        raise HTTPException(status_code=404, detail=f"Task {task_type} not found")

    await db.commit()
    logger.warning("Admin %s updated assignment for %s: %s", user.external_id, task_type, updates)

    return TaskAssignmentResponse(
        task_type=assignment.task_type,
        default_model_id=assignment.default_model_id,
        fallback_model_ids=assignment.fallback_model_ids or [],
        allowed_model_ids=assignment.allowed_model_ids or [],
        user_override_allowed=assignment.user_override_allowed,
        rollout_state=assignment.rollout_state,
        beta_only=assignment.beta_only,
    )


@router.get("/admin/health", response_model=list[ModelTaskHealthResponse])
async def admin_list_health(
    model_id: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_admin),
):
    """Admin: list model-task health states."""
    repo = MeteringRepository(db)
    entries = await repo.list_health(model_id=model_id)
    return [
        ModelTaskHealthResponse(
            model_id=h.model_id,
            task_type=h.task_type,
            status=h.status,
            consecutive_errors=h.consecutive_errors,
            rolling_error_rate=h.rolling_error_rate,
            cooldown_until=h.cooldown_until.isoformat() if h.cooldown_until else None,
            last_success_at=h.last_success_at.isoformat() if h.last_success_at else None,
            last_error_at=h.last_error_at.isoformat() if h.last_error_at else None,
            last_error_code=h.last_error_code,
            last_error_summary=h.last_error_summary,
            manual_override_reason=h.manual_override_reason,
        )
        for h in entries
    ]


@router.post("/admin/health/disable")
async def admin_disable_model_task(
    request: HealthActionRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_admin),
):
    """Admin: disable a model for a specific task."""
    svc = ModelHealthService(db)
    await svc.disable_model_task(request.model_id, request.task_type, request.reason)
    await db.commit()
    logger.warning(
        "Admin %s disabled %s for %s: %s",
        user.external_id, request.model_id, request.task_type, request.reason,
    )
    return {"status": "ok", "action": "disabled"}


@router.post("/admin/health/enable")
async def admin_enable_model_task(
    request: HealthActionRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_admin),
):
    """Admin: enable a model for a specific task."""
    svc = ModelHealthService(db)
    await svc.enable_model_task(request.model_id, request.task_type, request.reason)
    await db.commit()
    logger.warning(
        "Admin %s enabled %s for %s: %s",
        user.external_id, request.model_id, request.task_type, request.reason,
    )
    return {"status": "ok", "action": "enabled"}


@router.post("/admin/health/clear-cooldown")
async def admin_clear_cooldown(
    request: HealthActionRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_admin),
):
    """Admin: clear cooldown for a model-task pair."""
    svc = ModelHealthService(db)
    await svc.clear_cooldown(request.model_id, request.task_type, request.reason)
    await db.commit()
    logger.warning(
        "Admin %s cleared cooldown for %s/%s: %s",
        user.external_id, request.model_id, request.task_type, request.reason,
    )
    return {"status": "ok", "action": "cooldown_cleared"}

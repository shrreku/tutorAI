"""
Feature flags endpoint (PROD-014).

Returns current feature flag state for the authenticated user.
Flags are sourced from server-side config; PostHog overrides
can be layered in later.
"""

from fastapi import APIRouter, Depends

from app.config import settings
from app.api.deps import get_current_user

router = APIRouter(prefix="/flags", tags=["feature-flags"])


@router.get("")
async def get_feature_flags(user=Depends(get_current_user)):
    """Return all feature flags relevant to the current user."""
    return {
        "workspace_v2_enabled": settings.FF_WORKSPACE_V2_ENABLED,
        "active_learning_enabled": settings.FF_ACTIVE_LEARNING_ENABLED,
        "artifact_generation_enabled": settings.FF_ARTIFACT_GENERATION_ENABLED,
        "notebooks_enabled": True,
    }

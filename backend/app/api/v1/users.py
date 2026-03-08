import logging

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_auth
from app.db.database import get_db
from app.db.repositories.session_repo import UserProfileRepository
from app.models.session import UserProfile
from app.schemas.api import UserSettingsResponse, UserSettingsUpdateRequest
from app.services.account_cleanup import delete_user_account

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me/settings", response_model=UserSettingsResponse)
async def get_my_settings(
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Fetch current user-level settings."""
    user_repo = UserProfileRepository(db)
    consent_training_global, consent_preference_set = await user_repo.get_global_consent(user)
    return UserSettingsResponse(
        consent_training_global=consent_training_global,
        consent_preference_set=consent_preference_set,
    )


@router.patch("/me/settings", response_model=UserSettingsResponse)
async def update_my_settings(
    request: UserSettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Update mutable user-level settings."""
    user_repo = UserProfileRepository(db)
    updated = await user_repo.update_settings(
        user,
        consent_training_global=request.consent_training_global,
    )
    consent_training_global, consent_preference_set = await user_repo.get_global_consent(updated)
    return UserSettingsResponse(
        consent_training_global=consent_training_global,
        consent_preference_set=consent_preference_set,
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def delete_my_account(
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Delete the current user's account, uploads, and derived data."""
    logger.warning("Account deletion requested for user %s (%s)", user.id, user.email)
    await delete_user_account(db, user)
    return None

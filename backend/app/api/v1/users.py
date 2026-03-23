import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.api.deps import require_auth, is_admin_user
from app.db.database import get_db
from app.db.repositories.async_byok_repo import AsyncByokEscrowRepository
from app.db.repositories.session_repo import UserProfileRepository
from app.models.session import UserProfile
from app.schemas.api import (
    AsyncByokEscrowResponse,
    UserSettingsResponse,
    UserSettingsUpdateRequest,
)
from app.services.account_cleanup import delete_user_account
from app.services.async_byok_escrow import (
    AsyncByokEscrowService,
    async_byok_feature_available,
)
from app.services.ingestion.page_allowance import PageAllowanceService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me/settings", response_model=UserSettingsResponse)
async def get_my_settings(
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Fetch current user-level settings."""
    user_repo = UserProfileRepository(db)
    page_allowance = PageAllowanceService(db)
    user = await page_allowance.ensure_user_defaults(user)
    (
        consent_training_global,
        consent_preference_set,
    ) = await user_repo.get_global_consent(user)
    return UserSettingsResponse(
        consent_training_global=consent_training_global,
        consent_preference_set=consent_preference_set,
        is_admin=is_admin_user(user),
        async_byok_escrow_enabled=async_byok_feature_available(),
        async_byok_escrow_backend=settings.ASYNC_BYOK_ESCROW_BACKEND
        if async_byok_feature_available()
        else None,
        async_byok_escrow_ttl_minutes=settings.ASYNC_BYOK_ESCROW_TTL_MINUTES
        if async_byok_feature_available()
        else 0,
        parse_page_limit=int(user.parse_page_limit or 0),
        parse_page_used=int(user.parse_page_used or 0),
        parse_page_reserved=int(user.parse_page_reserved or 0),
        parse_page_remaining=page_allowance.remaining_pages_for(user),
    )


@router.patch("/me/settings", response_model=UserSettingsResponse)
async def update_my_settings(
    request: UserSettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    """Update mutable user-level settings."""
    user_repo = UserProfileRepository(db)
    page_allowance = PageAllowanceService(db)
    updated = await user_repo.update_settings(
        user,
        consent_training_global=request.consent_training_global,
    )
    updated = await page_allowance.ensure_user_defaults(updated)
    (
        consent_training_global,
        consent_preference_set,
    ) = await user_repo.get_global_consent(updated)
    return UserSettingsResponse(
        consent_training_global=consent_training_global,
        consent_preference_set=consent_preference_set,
        is_admin=is_admin_user(updated),
        async_byok_escrow_enabled=async_byok_feature_available(),
        async_byok_escrow_backend=settings.ASYNC_BYOK_ESCROW_BACKEND
        if async_byok_feature_available()
        else None,
        async_byok_escrow_ttl_minutes=settings.ASYNC_BYOK_ESCROW_TTL_MINUTES
        if async_byok_feature_available()
        else 0,
        parse_page_limit=int(updated.parse_page_limit or 0),
        parse_page_used=int(updated.parse_page_used or 0),
        parse_page_reserved=int(updated.parse_page_reserved or 0),
        parse_page_remaining=page_allowance.remaining_pages_for(updated),
    )


@router.get("/me/async-byok-escrows", response_model=list[AsyncByokEscrowResponse])
async def list_my_async_byok_escrows(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    if not async_byok_feature_available():
        return []

    service = AsyncByokEscrowService(AsyncByokEscrowRepository(db))
    escrows = await service.list_user_escrows(
        user.id, include_inactive=include_inactive
    )
    return [
        AsyncByokEscrowResponse(
            id=escrow.id,
            purpose_type=escrow.purpose_type,
            purpose_id=escrow.purpose_id,
            scope_type=escrow.scope_type,
            scope_key=escrow.scope_key,
            provider_name=escrow.provider_name,
            status=escrow.status,
            expires_at=escrow.expires_at,
            hard_delete_after=escrow.hard_delete_after,
            access_count=escrow.access_count,
            last_accessed_at=escrow.last_accessed_at,
            revoked_at=escrow.revoked_at,
            deleted_at=escrow.deleted_at,
            deletion_reason=escrow.deletion_reason,
        )
        for escrow in escrows
    ]


@router.post(
    "/me/async-byok-escrows/{escrow_id}:revoke", response_model=AsyncByokEscrowResponse
)
async def revoke_my_async_byok_escrow(
    escrow_id: UUID,
    db: AsyncSession = Depends(get_db),
    user: UserProfile = Depends(require_auth),
):
    if not async_byok_feature_available():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Async BYOK escrow is not enabled",
        )

    service = AsyncByokEscrowService(AsyncByokEscrowRepository(db))
    try:
        escrow = await service.revoke_user_escrow(escrow_id, user.id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)
        ) from exc

    return AsyncByokEscrowResponse(
        id=escrow.id,
        purpose_type=escrow.purpose_type,
        purpose_id=escrow.purpose_id,
        scope_type=escrow.scope_type,
        scope_key=escrow.scope_key,
        provider_name=escrow.provider_name,
        status=escrow.status,
        expires_at=escrow.expires_at,
        hard_delete_after=escrow.hard_delete_after,
        access_count=escrow.access_count,
        last_accessed_at=escrow.last_accessed_at,
        revoked_at=escrow.revoked_at,
        deleted_at=escrow.deleted_at,
        deletion_reason=escrow.deletion_reason,
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

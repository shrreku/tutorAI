import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.resource import Resource
from app.models.session import UserProfile
from app.services.storage.factory import create_storage_provider

logger = logging.getLogger(__name__)


async def delete_user_account(
    db: AsyncSession,
    user: UserProfile,
) -> dict[str, int]:
    """Delete a user's account and all owned uploads/derived data."""
    resource_result = await db.execute(
        select(Resource).where(Resource.owner_user_id == user.id)
    )
    owned_resources = list(resource_result.scalars().all())
    file_uris = [
        resource.file_path_or_uri
        for resource in owned_resources
        if resource.file_path_or_uri
    ]

    for resource in owned_resources:
        await db.delete(resource)

    await db.flush()
    await db.delete(user)
    await db.commit()

    deleted_files = 0
    storage = create_storage_provider(settings)
    for file_uri in file_uris:
        try:
            await storage.delete_file(file_uri)
            deleted_files += 1
        except Exception as exc:  # pragma: no cover - logged for operators
            logger.warning("Failed to delete user-owned file '%s': %s", file_uri, exc)

    logger.warning(
        "Deleted account %s with %d owned resources and %d/%d storage files removed",
        user.id,
        len(owned_resources),
        deleted_files,
        len(file_uris),
    )
    return {
        "resources_deleted": len(owned_resources),
        "files_deleted": deleted_files,
    }

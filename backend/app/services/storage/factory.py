import logging

from app.config import Settings
from app.services.storage.base import StorageProvider
from app.services.storage.local_provider import LocalStorageProvider

logger = logging.getLogger(__name__)


def create_storage_provider(config: Settings) -> StorageProvider:
    """Create a storage provider based on configuration."""
    if config.STORAGE_BACKEND == "s3":
        # S3 provider would be imported and used here
        # from app.services.storage.s3_provider import S3StorageProvider
        # return S3StorageProvider(...)
        logger.warning("S3 storage not implemented, falling back to local")
    
    return LocalStorageProvider(config.STORAGE_LOCAL_DIR)

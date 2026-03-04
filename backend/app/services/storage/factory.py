import logging

from app.config import Settings
from app.services.storage.base import StorageProvider
from app.services.storage.local_provider import LocalStorageProvider

logger = logging.getLogger(__name__)


def create_storage_provider(config: Settings) -> StorageProvider:
    """Create a storage provider based on configuration.

    - ``STORAGE_BACKEND=s3`` → S3-compatible (AWS / MinIO / R2)
    - anything else            → local disk
    """
    if config.STORAGE_BACKEND == "s3":
        if not config.S3_BUCKET_NAME:
            logger.warning("S3 backend selected but S3_BUCKET_NAME is not set – falling back to local")
            return LocalStorageProvider(config.STORAGE_LOCAL_DIR)

        from app.services.storage.s3_provider import S3StorageProvider

        return S3StorageProvider(
            bucket_name=config.S3_BUCKET_NAME,
            region=config.S3_REGION,
            endpoint_url=config.MINIO_ENDPOINT,
            access_key=config.MINIO_ACCESS_KEY,
            secret_key=config.MINIO_SECRET_KEY,
        )

    return LocalStorageProvider(config.STORAGE_LOCAL_DIR)

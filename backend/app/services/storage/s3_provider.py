"""
S3-compatible storage provider for production uploads.

Works with AWS S3, MinIO, Cloudflare R2, and similar services.
Respects the following settings:
  - S3_BUCKET_NAME
  - S3_REGION
  - MINIO_ENDPOINT (if using MinIO / R2)
  - MINIO_ACCESS_KEY / MINIO_SECRET_KEY
"""

import asyncio
import logging
import uuid
from pathlib import Path
from typing import Optional

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from app.services.storage.base import StorageProvider

logger = logging.getLogger(__name__)


class S3StorageProvider(StorageProvider):
    """S3-compatible storage backend."""

    def __init__(
        self,
        bucket_name: str,
        region: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        prefix: str = "uploads",
    ):
        self.bucket_name = bucket_name
        self.prefix = prefix

        kwargs: dict = {}
        if endpoint_url:
            kwargs["endpoint_url"] = endpoint_url
        if region:
            kwargs["region_name"] = region
        if access_key and secret_key:
            kwargs["aws_access_key_id"] = access_key
            kwargs["aws_secret_access_key"] = secret_key

        self._client = boto3.client(
            "s3",
            config=BotoConfig(
                signature_version="s3v4",
                connect_timeout=5,
                read_timeout=30,
                retries={"max_attempts": 3, "mode": "standard"},
            ),
            **kwargs,
        )

        # Ensure bucket exists (useful for MinIO dev)
        try:
            self._client.head_bucket(Bucket=bucket_name)
        except ClientError:
            logger.info(f"Creating bucket '{bucket_name}'")
            try:
                self._client.create_bucket(Bucket=bucket_name)
            except ClientError as exc:
                logger.warning(f"Could not create bucket: {exc}")

    def _key(self, filename: str) -> str:
        unique = f"{uuid.uuid4()}{Path(filename).suffix}"
        return f"{self.prefix}/{unique}" if self.prefix else unique

    # --- StorageProvider interface ---

    async def save_file(self, file_bytes: bytes, filename: str) -> str:
        key = self._key(filename)
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self.bucket_name,
            Key=key,
            Body=file_bytes,
        )
        uri = f"s3://{self.bucket_name}/{key}"
        logger.debug(f"Saved {len(file_bytes)} bytes → {uri}")
        return uri

    async def open_file(self, file_uri: str) -> bytes:
        bucket, key = self._parse_uri(file_uri)
        response = await asyncio.to_thread(
            self._client.get_object,
            Bucket=bucket,
            Key=key,
        )
        return await asyncio.to_thread(response["Body"].read)

    async def delete_file(self, file_uri: str) -> None:
        bucket, key = self._parse_uri(file_uri)
        await asyncio.to_thread(
            self._client.delete_object,
            Bucket=bucket,
            Key=key,
        )

    async def file_exists(self, file_uri: str) -> bool:
        bucket, key = self._parse_uri(file_uri)
        try:
            await asyncio.to_thread(
                self._client.head_object,
                Bucket=bucket,
                Key=key,
            )
            return True
        except ClientError:
            return False

    # --- Signed URL for direct browser download (optional) ---

    def generate_presigned_url(self, file_uri: str, expires_in: int = 3600) -> str:
        bucket, key = self._parse_uri(file_uri)
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    # --- Helpers ---

    @staticmethod
    def _parse_uri(uri: str) -> tuple[str, str]:
        """Parse ``s3://bucket/key`` into (bucket, key)."""
        if uri.startswith("s3://"):
            uri = uri[5:]
        parts = uri.split("/", 1)
        if len(parts) != 2:
            raise ValueError(f"Invalid S3 URI: {uri}")
        return parts[0], parts[1]

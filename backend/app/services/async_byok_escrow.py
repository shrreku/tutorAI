import base64
import hashlib
import json
import logging
import os
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol
from uuid import UUID

import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import Settings, settings
from app.db.repositories.async_byok_repo import AsyncByokEscrowRepository
from app.models.async_byok import AsyncByokEscrow

logger = logging.getLogger(__name__)


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8")


def _urlsafe_b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value.encode("utf-8"))


def _standard_b64encode(data: bytes) -> str:
    return base64.b64encode(data).decode("utf-8")


def _standard_b64decode(value: str) -> bytes:
    return base64.b64decode(value.encode("utf-8"))


def async_byok_feature_available(config: Settings = settings) -> bool:
    if not config.ASYNC_BYOK_ESCROW_ENABLED:
        return False
    try:
        validate_async_byok_escrow_config(config)
    except RuntimeError:
        return False
    return True


def validate_async_byok_escrow_config(config: Settings = settings) -> None:
    if not config.ASYNC_BYOK_ESCROW_ENABLED:
        return
    if config.ASYNC_BYOK_ESCROW_TTL_MINUTES <= 0:
        raise RuntimeError("ASYNC_BYOK_ESCROW_TTL_MINUTES must be positive")
    if config.ASYNC_BYOK_ESCROW_HARD_MAX_MINUTES < config.ASYNC_BYOK_ESCROW_TTL_MINUTES:
        raise RuntimeError(
            "ASYNC_BYOK_ESCROW_HARD_MAX_MINUTES must be >= ASYNC_BYOK_ESCROW_TTL_MINUTES"
        )
    backend = (config.ASYNC_BYOK_ESCROW_BACKEND or "").strip().lower()
    if backend == "local":
        if not (config.ASYNC_BYOK_LOCAL_KEK or "").strip():
            raise RuntimeError(
                "ASYNC_BYOK_LOCAL_KEK is required when ASYNC_BYOK_ESCROW_BACKEND=local"
            )
        raw_key = _urlsafe_b64decode(config.ASYNC_BYOK_LOCAL_KEK.strip())
        if len(raw_key) != 32:
            raise RuntimeError("ASYNC_BYOK_LOCAL_KEK must decode to 32 bytes")
        return
    if backend == "vault_transit":
        missing = []
        if not (config.ASYNC_BYOK_VAULT_URL or "").strip():
            missing.append("ASYNC_BYOK_VAULT_URL")
        if not (config.ASYNC_BYOK_VAULT_TOKEN or "").strip():
            missing.append("ASYNC_BYOK_VAULT_TOKEN")
        if not (config.ASYNC_BYOK_VAULT_TRANSIT_KEY_NAME or "").strip():
            missing.append("ASYNC_BYOK_VAULT_TRANSIT_KEY_NAME")
        if missing:
            raise RuntimeError(
                "Async BYOK escrow backend is incomplete: missing " + ", ".join(missing)
            )
        return
    raise RuntimeError(
        f"Unsupported ASYNC_BYOK_ESCROW_BACKEND: {config.ASYNC_BYOK_ESCROW_BACKEND}"
    )


class AsyncByokKeyProvider(Protocol):
    backend_name: str

    async def wrap_dek(self, dek: bytes) -> tuple[str, str, str | None]: ...

    async def unwrap_dek(self, wrapped_dek: str) -> bytes: ...


class LocalAsyncByokKeyProvider:
    backend_name = "local"

    def __init__(self, kek_b64: str):
        self._raw_key = _urlsafe_b64decode(kek_b64.strip())
        self._cipher = AESGCM(self._raw_key)

    async def wrap_dek(self, dek: bytes) -> tuple[str, str, str | None]:
        nonce = os.urandom(12)
        ciphertext = self._cipher.encrypt(nonce, dek, None)
        wrapped = (
            f"local:v1:{_urlsafe_b64encode(nonce)}:{_urlsafe_b64encode(ciphertext)}"
        )
        return wrapped, "local-kek", "v1"

    async def unwrap_dek(self, wrapped_dek: str) -> bytes:
        parts = wrapped_dek.split(":", 3)
        if len(parts) != 4 or parts[0] != "local":
            raise RuntimeError("Unsupported local wrapped DEK format")
        nonce = _urlsafe_b64decode(parts[2])
        ciphertext = _urlsafe_b64decode(parts[3])
        return self._cipher.decrypt(nonce, ciphertext, None)


class VaultTransitAsyncByokKeyProvider:
    backend_name = "vault_transit"

    def __init__(self, config: Settings):
        self._base_url = config.ASYNC_BYOK_VAULT_URL.rstrip("/")
        self._token = config.ASYNC_BYOK_VAULT_TOKEN
        self._key_name = config.ASYNC_BYOK_VAULT_TRANSIT_KEY_NAME
        self._timeout = config.ASYNC_BYOK_VAULT_TIMEOUT_SECONDS

    async def wrap_dek(self, dek: bytes) -> tuple[str, str, str | None]:
        payload = {"plaintext": _standard_b64encode(dek)}
        data = await self._request(
            "POST", f"/v1/transit/encrypt/{self._key_name}", payload
        )
        return (
            str(data["ciphertext"]),
            self._key_name,
            str(data.get("key_version"))
            if data.get("key_version") is not None
            else None,
        )

    async def unwrap_dek(self, wrapped_dek: str) -> bytes:
        payload = {"ciphertext": wrapped_dek}
        data = await self._request(
            "POST", f"/v1/transit/decrypt/{self._key_name}", payload
        )
        return _standard_b64decode(str(data["plaintext"]))

    async def _request(self, method: str, path: str, payload: dict) -> dict:
        headers = {"X-Vault-Token": self._token}
        async with httpx.AsyncClient(
            base_url=self._base_url, timeout=self._timeout
        ) as client:
            response = await client.request(method, path, headers=headers, json=payload)
        response.raise_for_status()
        body = response.json()
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, dict):
            raise RuntimeError("Vault Transit response missing data payload")
        return data


def build_async_byok_key_provider(config: Settings = settings) -> AsyncByokKeyProvider:
    validate_async_byok_escrow_config(config)
    backend = config.ASYNC_BYOK_ESCROW_BACKEND.strip().lower()
    if backend == "local":
        return LocalAsyncByokKeyProvider(config.ASYNC_BYOK_LOCAL_KEK)
    if backend == "vault_transit":
        return VaultTransitAsyncByokKeyProvider(config)
    raise RuntimeError(
        f"Unsupported async BYOK escrow backend: {config.ASYNC_BYOK_ESCROW_BACKEND}"
    )


@dataclass
class AsyncByokResolvedSecret:
    api_key: str
    api_base_url: str | None
    provider_name: str | None
    escrow_id: str


class AsyncByokEscrowService:
    def __init__(self, repo: AsyncByokEscrowRepository, *, config: Settings = settings):
        self.repo = repo
        self.config = config
        self.key_provider = build_async_byok_key_provider(config)

    @staticmethod
    def compute_provider_name(base_url: str | None) -> str:
        if not base_url:
            return "openai-compatible"
        hostname = base_url.split("//", 1)[-1].split("/", 1)[0].lower()
        if "openai" in hostname:
            return "openai-compatible"
        if "openrouter" in hostname:
            return "openrouter"
        if "anthropic" in hostname:
            return "anthropic-compatible"
        if "google" in hostname or "gemini" in hostname:
            return "google-compatible"
        return hostname

    async def create_ingestion_escrow(
        self,
        *,
        user_id: UUID,
        resource_id: UUID,
        job_id: UUID,
        byok_api_key: str,
        byok_api_base_url: str | None,
    ) -> AsyncByokEscrow:
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=self.config.ASYNC_BYOK_ESCROW_TTL_MINUTES)
        hard_delete_after = now + timedelta(
            minutes=self.config.ASYNC_BYOK_ESCROW_RETENTION_MINUTES
        )
        aad_payload = {
            "user_id": str(user_id),
            "purpose_type": "ingestion",
            "purpose_id": str(job_id),
            "scope_type": "resource",
            "scope_key": str(resource_id),
        }
        aad_bytes = json.dumps(
            aad_payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        aad_hash = hashlib.sha256(aad_bytes).hexdigest()

        plaintext = json.dumps(
            {
                "provider_api_key": byok_api_key,
                "provider_base_url": byok_api_base_url,
                "provider_name": self.compute_provider_name(byok_api_base_url),
                "created_by_user_id": str(user_id),
                "created_at": now.isoformat(),
                "expires_at": expires_at.isoformat(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        dek = secrets.token_bytes(32)
        payload_nonce = os.urandom(12)
        payload_cipher = AESGCM(dek)
        ciphertext = payload_cipher.encrypt(payload_nonce, plaintext, aad_bytes)
        wrapped_dek, key_reference, key_version = await self.key_provider.wrap_dek(dek)

        escrow = AsyncByokEscrow(
            user_id=user_id,
            purpose_type="ingestion",
            purpose_id=str(job_id),
            scope_type="resource",
            scope_key=str(resource_id),
            provider_name=self.compute_provider_name(byok_api_base_url),
            ciphertext_blob=ciphertext,
            nonce=payload_nonce,
            wrapped_dek=wrapped_dek,
            key_backend=self.key_provider.backend_name,
            key_reference=key_reference,
            key_version=key_version,
            aad_hash=aad_hash,
            status="active",
            expires_at=expires_at,
            hard_delete_after=hard_delete_after,
        )
        return await self.repo.create(escrow)

    async def decrypt_for_ingestion(
        self, *, escrow_id: UUID, resource_id: UUID, job_id: UUID
    ) -> AsyncByokResolvedSecret:
        await self.repo.expire_due()
        escrow = await self.repo.get_for_decrypt(
            escrow_id, purpose_type="ingestion", purpose_id=str(job_id)
        )
        if escrow is None:
            raise RuntimeError("Async BYOK escrow not found for this job")
        if escrow.status != "active":
            raise RuntimeError(f"Async BYOK escrow is not active: {escrow.status}")
        if escrow.scope_type != "resource" or escrow.scope_key != str(resource_id):
            raise RuntimeError("Async BYOK escrow scope mismatch")

        aad_payload = {
            "user_id": str(escrow.user_id),
            "purpose_type": escrow.purpose_type,
            "purpose_id": escrow.purpose_id,
            "scope_type": escrow.scope_type,
            "scope_key": escrow.scope_key,
        }
        aad_bytes = json.dumps(
            aad_payload, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if hashlib.sha256(aad_bytes).hexdigest() != escrow.aad_hash:
            raise RuntimeError("Async BYOK escrow AAD hash mismatch")

        dek = await self.key_provider.unwrap_dek(escrow.wrapped_dek)
        plaintext = AESGCM(dek).decrypt(escrow.nonce, escrow.ciphertext_blob, aad_bytes)
        payload = json.loads(plaintext.decode("utf-8"))
        await self.repo.mark_accessed(escrow)
        return AsyncByokResolvedSecret(
            api_key=str(payload["provider_api_key"]),
            api_base_url=payload.get("provider_base_url"),
            provider_name=payload.get("provider_name"),
            escrow_id=str(escrow.id),
        )

    async def list_user_escrows(
        self, user_id: UUID, *, include_inactive: bool = False
    ) -> list[AsyncByokEscrow]:
        await self.repo.expire_due()
        return await self.repo.list_for_user(user_id, include_inactive=include_inactive)

    async def revoke_user_escrow(
        self, escrow_id: UUID, user_id: UUID
    ) -> AsyncByokEscrow:
        await self.repo.expire_due()
        escrow = await self.repo.get_for_user(escrow_id, user_id)
        if escrow is None:
            raise RuntimeError("Async BYOK escrow not found")
        if escrow.status != "active":
            return escrow
        await self.repo.revoke(escrow, reason="user_revoked")
        logger.warning(
            "Async BYOK escrow revoked by user %s for escrow %s", user_id, escrow_id
        )
        return escrow

    async def finalize_job_escrow(
        self, escrow_id: UUID, *, reason: str, success: bool
    ) -> None:
        escrow = await self.repo.get_by_id(escrow_id)
        if escrow is None or escrow.status != "active":
            return
        await self.repo.finalize_terminal(escrow, reason=reason, success=success)

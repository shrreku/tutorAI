import asyncio
import base64
import os
from uuid import uuid4

from app.config import settings
from app.services.async_byok_escrow import AsyncByokEscrowService


class _FakeRepo:
    def __init__(self):
        self.rows = {}

    async def create(self, escrow):
        if escrow.id is None:
            escrow.id = uuid4()
        self.rows[escrow.id] = escrow
        return escrow

    async def expire_due(self, **_kwargs):
        return 0

    async def get_for_decrypt(self, escrow_id, *, purpose_type, purpose_id):
        escrow = self.rows.get(escrow_id)
        if (
            escrow
            and escrow.purpose_type == purpose_type
            and escrow.purpose_id == purpose_id
        ):
            return escrow
        return None

    async def mark_accessed(self, escrow, **_kwargs):
        escrow.access_count = int(escrow.access_count or 0) + 1

    async def list_for_user(self, user_id, *, include_inactive=False, limit=50):
        del include_inactive, limit
        return [row for row in self.rows.values() if row.user_id == user_id]

    async def get_for_user(self, escrow_id, user_id):
        escrow = self.rows.get(escrow_id)
        if escrow and escrow.user_id == user_id:
            return escrow
        return None

    async def revoke(self, escrow, *, reason, **_kwargs):
        escrow.status = "revoked"
        escrow.deletion_reason = reason

    async def get_by_id(self, escrow_id):
        return self.rows.get(escrow_id)

    async def finalize_terminal(self, escrow, *, reason, success, **_kwargs):
        escrow.status = "consumed" if success else "deleted"
        escrow.deletion_reason = reason


def test_async_byok_escrow_service_round_trip(monkeypatch):
    monkeypatch.setattr(settings, "ASYNC_BYOK_ESCROW_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ASYNC_BYOK_ESCROW_BACKEND", "local", raising=False)
    monkeypatch.setattr(
        settings,
        "ASYNC_BYOK_LOCAL_KEK",
        base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8"),
        raising=False,
    )

    repo = _FakeRepo()
    service = AsyncByokEscrowService(repo)
    user_id = uuid4()
    resource_id = uuid4()
    job_id = uuid4()

    escrow = asyncio.run(
        service.create_ingestion_escrow(
            user_id=user_id,
            resource_id=resource_id,
            job_id=job_id,
            byok_api_key="sk-test-user-key",
            byok_api_base_url="https://api.openai.com/v1",
        )
    )

    resolved = asyncio.run(
        service.decrypt_for_ingestion(
            escrow_id=escrow.id,
            resource_id=resource_id,
            job_id=job_id,
        )
    )

    assert resolved.api_key == "sk-test-user-key"
    assert resolved.api_base_url == "https://api.openai.com/v1"
    assert resolved.provider_name == "openai-compatible"
    assert repo.rows[escrow.id].access_count == 1


def test_async_byok_escrow_revoke_marks_row_revoked(monkeypatch):
    monkeypatch.setattr(settings, "ASYNC_BYOK_ESCROW_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ASYNC_BYOK_ESCROW_BACKEND", "local", raising=False)
    monkeypatch.setattr(
        settings,
        "ASYNC_BYOK_LOCAL_KEK",
        base64.urlsafe_b64encode(os.urandom(32)).decode("utf-8"),
        raising=False,
    )

    repo = _FakeRepo()
    service = AsyncByokEscrowService(repo)
    user_id = uuid4()
    resource_id = uuid4()
    job_id = uuid4()
    escrow = asyncio.run(
        service.create_ingestion_escrow(
            user_id=user_id,
            resource_id=resource_id,
            job_id=job_id,
            byok_api_key="sk-test-user-key",
            byok_api_base_url=None,
        )
    )

    revoked = asyncio.run(service.revoke_user_escrow(escrow.id, user_id))

    assert revoked.status == "revoked"
    assert revoked.deletion_reason == "user_revoked"

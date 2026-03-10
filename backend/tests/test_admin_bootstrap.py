import asyncio
from types import SimpleNamespace

from app.config import settings
from app.services import admin_bootstrap as bootstrap_module


class _FakeSession:
    def __init__(self):
        self.added = []
        self.commit_calls = 0

    def add(self, obj):
        self.added.append(obj)

    async def commit(self):
        self.commit_calls += 1


class _FakeSessionFactory:
    def __init__(self, session):
        self._session = session

    def __call__(self):
        return self

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        return False


def test_ensure_bootstrap_admin_creates_account_when_missing(monkeypatch):
    fake_session = _FakeSession()

    class _Repo:
        def __init__(self, _db):
            pass

        async def get_by_email(self, _email):
            return None

        async def get_by_external_id(self, _external_id):
            return None

    monkeypatch.setattr(settings, "AUTH_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ADMIN_EXTERNAL_ID", "admin@example.com", raising=False)
    monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_EMAIL", "admin@example.com", raising=False)
    monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_PASSWORD", "Password123!", raising=False)
    monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_DISPLAY_NAME", "Prod Admin", raising=False)
    monkeypatch.setattr(bootstrap_module, "UserProfileRepository", _Repo)
    monkeypatch.setattr(bootstrap_module, "async_session_factory", _FakeSessionFactory(fake_session))

    asyncio.run(bootstrap_module.ensure_bootstrap_admin())

    assert fake_session.commit_calls == 1
    assert fake_session.added[0].email == "admin@example.com"
    assert fake_session.added[0].external_id == "admin@example.com"


def test_ensure_bootstrap_admin_updates_existing_account(monkeypatch):
    fake_session = _FakeSession()
    existing = SimpleNamespace(
        external_id="admin@example.com",
        email="admin@example.com",
        display_name="Old",
        password_hash="old-hash",
        preferences={},
    )

    class _Repo:
        def __init__(self, _db):
            pass

        async def get_by_email(self, _email):
            return existing

        async def get_by_external_id(self, _external_id):
            return existing

    monkeypatch.setattr(settings, "AUTH_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "ADMIN_EXTERNAL_ID", "admin@example.com", raising=False)
    monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_EMAIL", "admin@example.com", raising=False)
    monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_PASSWORD", "Password123!", raising=False)
    monkeypatch.setattr(settings, "ADMIN_BOOTSTRAP_DISPLAY_NAME", "Prod Admin", raising=False)
    monkeypatch.setattr(bootstrap_module, "UserProfileRepository", _Repo)
    monkeypatch.setattr(bootstrap_module, "async_session_factory", _FakeSessionFactory(fake_session))

    asyncio.run(bootstrap_module.ensure_bootstrap_admin())

    assert fake_session.commit_calls == 1
    assert existing.display_name == "Prod Admin"
    assert existing.password_hash != "old-hash"
    assert existing.preferences["admin_bootstrapped"] is True
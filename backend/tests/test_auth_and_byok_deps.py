import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.api import deps as deps_module
from app.config import settings


def test_get_byok_api_key_returns_empty_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "BYOK_ENABLED", False, raising=False)

    payload = deps_module.get_byok_api_key(
        x_llm_api_key="secret",
        x_llm_api_base_url="https://api.example.com/v1",
    )

    assert payload == {"api_key": None, "api_base_url": None}


def test_get_byok_api_key_rejects_http_when_https_required(monkeypatch):
    monkeypatch.setattr(settings, "BYOK_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "BYOK_REQUIRE_HTTPS", True, raising=False)
    monkeypatch.setattr(settings, "BYOK_ALLOW_PRIVATE_BASE_URLS", True, raising=False)

    with pytest.raises(HTTPException) as exc:
        deps_module.get_byok_api_key(
            x_llm_api_key="secret",
            x_llm_api_base_url="http://api.example.com/v1",
        )

    assert exc.value.status_code == 400
    assert "https" in str(exc.value.detail)


def test_get_byok_api_key_rejects_private_hosts_by_default(monkeypatch):
    monkeypatch.setattr(settings, "BYOK_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "BYOK_REQUIRE_HTTPS", False, raising=False)
    monkeypatch.setattr(settings, "BYOK_ALLOW_PRIVATE_BASE_URLS", False, raising=False)

    with pytest.raises(HTTPException) as exc:
        deps_module.get_byok_api_key(
            x_llm_api_key="secret",
            x_llm_api_base_url="http://localhost:8080/v1",
        )

    assert exc.value.status_code == 400
    assert "not allowed" in str(exc.value.detail)


def test_get_byok_api_key_accepts_valid_public_https_url(monkeypatch):
    monkeypatch.setattr(settings, "BYOK_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "BYOK_REQUIRE_HTTPS", True, raising=False)
    monkeypatch.setattr(settings, "BYOK_ALLOW_PRIVATE_BASE_URLS", False, raising=False)

    payload = deps_module.get_byok_api_key(
        x_llm_api_key="secret",
        x_llm_api_base_url="https://api.openai.com/v1/",
    )

    assert payload["api_key"] == "secret"
    assert payload["api_base_url"] == "https://api.openai.com/v1"


def test_check_auth_rate_limit_raises_when_threshold_reached(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", True, raising=False)
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_REQUESTS_PER_MINUTE", 1, raising=False)
    deps_module._auth_rate_limit_store.clear()

    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.8"))
    asyncio.run(deps_module.check_auth_rate_limit(request))

    with pytest.raises(HTTPException) as exc:
        asyncio.run(deps_module.check_auth_rate_limit(request))

    assert exc.value.status_code == 429
    assert "Too many authentication attempts" in str(exc.value.detail)


def test_check_auth_rate_limit_noop_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "RATE_LIMIT_ENABLED", False, raising=False)
    deps_module._auth_rate_limit_store.clear()

    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.9"))
    asyncio.run(deps_module.check_auth_rate_limit(request))
    asyncio.run(deps_module.check_auth_rate_limit(request))


def test_require_notebooks_enabled_raises_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "FEATURE_NOTEBOOKS_ENABLED", False, raising=False)

    with pytest.raises(HTTPException) as exc:
        deps_module.require_notebooks_enabled()

    assert exc.value.status_code == 404
    assert "disabled" in str(exc.value.detail)

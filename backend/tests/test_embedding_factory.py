import asyncio
from types import SimpleNamespace

import pytest

import app.services.embedding.factory as factory_module
import app.services.embedding.remote_provider as remote_provider_module
from app.services.embedding.factory import (
    MockEmbeddingProvider,
    create_embedding_provider,
)
from app.services.embedding.remote_provider import RemoteEmbeddingProvider


class _DummyResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _DummyAsyncClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers or {}, "json": json})
        if not self.responses:
            raise AssertionError("No dummy responses queued")
        return _DummyResponse(self.responses.pop(0))

    async def aclose(self):
        return None


@pytest.fixture(autouse=True)
def _reset_embedding_provider_cache():
    factory_module._embedding_provider = None
    yield
    factory_module._embedding_provider = None


def test_create_embedding_provider_returns_mock_for_mock_backend():
    config = SimpleNamespace(
        EMBEDDING_PROVIDER="mock",
        EMBEDDING_MODEL_ID="test-model",
        EMBEDDING_DIMENSION=384,
        EMBEDDING_API_KEY=None,
        EMBEDDING_API_BASE_URL=None,
    )

    provider = create_embedding_provider(config)

    assert isinstance(provider, MockEmbeddingProvider)
    assert provider.model_id == "test-model"
    assert provider.dimension == 384


def test_create_embedding_provider_returns_remote_provider_for_gemini():
    config = SimpleNamespace(
        EMBEDDING_PROVIDER="gemini",
        EMBEDDING_MODEL_ID="gemini-embedding-001",
        EMBEDDING_DIMENSION=384,
        EMBEDDING_API_KEY="test-key",
        EMBEDDING_API_BASE_URL="https://generativelanguage.googleapis.com/v1beta",
    )

    provider = create_embedding_provider(config)

    assert isinstance(provider, RemoteEmbeddingProvider)
    assert provider.model_id == "gemini-embedding-001"
    assert provider.dimension == 384


def test_create_embedding_provider_rejects_unknown_backend():
    config = SimpleNamespace(
        EMBEDDING_PROVIDER="unknown",
        EMBEDDING_MODEL_ID="test-model",
        EMBEDDING_DIMENSION=384,
        EMBEDDING_API_KEY=None,
        EMBEDDING_API_BASE_URL=None,
    )

    with pytest.raises(ValueError, match="Unsupported EMBEDDING_PROVIDER"):
        create_embedding_provider(config)


def test_create_embedding_provider_rejects_local_backend():
    config = SimpleNamespace(
        EMBEDDING_PROVIDER="local",
        EMBEDDING_MODEL_ID="test-model",
        EMBEDDING_DIMENSION=384,
        EMBEDDING_API_KEY=None,
        EMBEDDING_API_BASE_URL=None,
    )

    with pytest.raises(
        ValueError, match="Local embedding providers are no longer supported"
    ):
        create_embedding_provider(config)


def test_remote_gemini_single_embed_uses_dimension_override(monkeypatch):
    dummy_client = _DummyAsyncClient([{"embedding": {"values": [0.1, 0.2, 0.3, 0.4]}}])
    monkeypatch.setattr(
        remote_provider_module,
        "httpx",
        SimpleNamespace(AsyncClient=lambda timeout: dummy_client),
    )

    provider = RemoteEmbeddingProvider(
        provider="gemini",
        model_id="gemini-embedding-001",
        dimension=4,
        api_key="test-key",
    )

    result = asyncio.run(provider.embed(["hello world"]))

    assert result == [[0.1, 0.2, 0.3, 0.4]]
    assert dummy_client.calls[0]["url"].endswith(
        "/models/gemini-embedding-001:embedContent"
    )
    assert dummy_client.calls[0]["headers"]["x-goog-api-key"] == "test-key"
    assert dummy_client.calls[0]["json"]["outputDimensionality"] == 4
    assert dummy_client.calls[0]["json"]["content"] == {
        "parts": [{"text": "hello world"}]
    }


def test_remote_gemini_batch_embed_preserves_order(monkeypatch):
    dummy_client = _DummyAsyncClient(
        [{"embeddings": [{"values": [1.0, 0.0]}, {"values": [0.0, 1.0]}]}]
    )
    monkeypatch.setattr(
        remote_provider_module,
        "httpx",
        SimpleNamespace(AsyncClient=lambda timeout: dummy_client),
    )

    provider = RemoteEmbeddingProvider(
        provider="gemini",
        model_id="models/gemini-embedding-001",
        dimension=2,
        api_key="test-key",
    )

    result = asyncio.run(provider.embed(["first", "second"]))

    assert result == [[1.0, 0.0], [0.0, 1.0]]
    request_payload = dummy_client.calls[0]["json"]
    assert len(request_payload["requests"]) == 2
    assert request_payload["requests"][0]["outputDimensionality"] == 2
    assert request_payload["requests"][0]["content"] == {"parts": [{"text": "first"}]}
    assert request_payload["requests"][1]["content"] == {"parts": [{"text": "second"}]}


def test_remote_openrouter_embed_uses_openai_compatible_shape(monkeypatch):
    dummy_client = _DummyAsyncClient(
        [{"data": [{"embedding": [0.5, 0.6, 0.7]}, {"embedding": [0.8, 0.9, 1.0]}]}]
    )
    monkeypatch.setattr(
        remote_provider_module,
        "httpx",
        SimpleNamespace(AsyncClient=lambda timeout: dummy_client),
    )

    provider = RemoteEmbeddingProvider(
        provider="openrouter",
        model_id="google/gemini-embedding-001",
        dimension=3,
        api_key="router-key",
    )

    result = asyncio.run(provider.embed(["alpha", "beta"]))

    assert result == [[0.5, 0.6, 0.7], [0.8, 0.9, 1.0]]
    assert dummy_client.calls[0]["url"] == "https://openrouter.ai/api/v1/embeddings"
    assert dummy_client.calls[0]["headers"]["Authorization"] == "Bearer router-key"
    assert dummy_client.calls[0]["json"] == {
        "model": "google/gemini-embedding-001",
        "input": ["alpha", "beta"],
        "encoding_format": "float",
        "dimensions": 3,
    }


def test_remote_provider_rejects_dimension_mismatch(monkeypatch):
    dummy_client = _DummyAsyncClient([{"embedding": {"values": [0.1, 0.2]}}])
    monkeypatch.setattr(
        remote_provider_module,
        "httpx",
        SimpleNamespace(AsyncClient=lambda timeout: dummy_client),
    )

    provider = RemoteEmbeddingProvider(
        provider="gemini",
        model_id="gemini-embedding-001",
        dimension=3,
        api_key="test-key",
    )

    with pytest.raises(ValueError, match="Embedding dimension mismatch"):
        asyncio.run(provider.embed(["hello world"]))


def test_remote_provider_rejects_count_mismatch(monkeypatch):
    dummy_client = _DummyAsyncClient([{"data": [{"embedding": [0.1, 0.2, 0.3]}]}])
    monkeypatch.setattr(
        remote_provider_module,
        "httpx",
        SimpleNamespace(AsyncClient=lambda timeout: dummy_client),
    )

    provider = RemoteEmbeddingProvider(
        provider="openrouter",
        model_id="google/gemini-embedding-001",
        dimension=3,
        api_key="router-key",
    )

    with pytest.raises(ValueError, match="Embedding response count mismatch"):
        asyncio.run(provider.embed(["first", "second"]))

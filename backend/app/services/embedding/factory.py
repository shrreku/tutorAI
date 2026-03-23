import logging
import threading

from app.config import Settings
from app.services.embedding.base import BaseEmbeddingProvider

logger = logging.getLogger(__name__)

# ── Singleton cache ───────────────────────────────────────────────────
_embedding_provider: BaseEmbeddingProvider | None = None
_embedding_lock = threading.Lock()


class MockEmbeddingProvider(BaseEmbeddingProvider):
    """Mock embedding provider for when sentence-transformers is not available."""

    def __init__(self, model_id: str, dimension: int = 384):
        self._model_id = model_id
        self._dimension = dimension

    @property
    def model_id(self) -> str:
        return self._model_id

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Return zero vectors for testing."""
        import random

        return [
            [random.uniform(-0.1, 0.1) for _ in range(self._dimension)] for _ in texts
        ]


def create_embedding_provider(config: Settings) -> BaseEmbeddingProvider:
    """Return a cached embedding provider (singleton).

    The SentenceTransformer model weights are heavy to load, so we
    instantiate the provider once and reuse it for all subsequent calls.
    """
    global _embedding_provider

    if _embedding_provider is not None:
        return _embedding_provider

    with _embedding_lock:
        # Double-check after acquiring the lock
        if _embedding_provider is not None:
            return _embedding_provider

        provider_name = (config.EMBEDDING_PROVIDER or "local").strip().lower()

        if provider_name == "mock":
            _embedding_provider = MockEmbeddingProvider(
                model_id=config.EMBEDDING_MODEL_ID,
                dimension=config.EMBEDDING_DIMENSION,
            )
            return _embedding_provider

        if provider_name in {"gemini", "openrouter"}:
            from app.services.embedding.remote_provider import RemoteEmbeddingProvider

            _embedding_provider = RemoteEmbeddingProvider(
                provider=provider_name,
                model_id=config.EMBEDDING_MODEL_ID,
                dimension=config.EMBEDDING_DIMENSION,
                api_key=config.EMBEDDING_API_KEY or "",
                base_url=config.EMBEDDING_API_BASE_URL,
            )
            return _embedding_provider

        if provider_name == "local":
            raise ValueError(
                "Local embedding providers are no longer supported. "
                "Set EMBEDDING_PROVIDER to openrouter, gemini, or mock."
            )

        raise ValueError(
            f"Unsupported EMBEDDING_PROVIDER '{config.EMBEDDING_PROVIDER}'. "
            "Expected one of: gemini, openrouter, mock."
        )

    return _embedding_provider

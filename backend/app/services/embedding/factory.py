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

        try:
            from app.services.embedding.local_provider import LocalEmbeddingProvider

            provider = LocalEmbeddingProvider(model_id=config.EMBEDDING_MODEL_ID)

            if provider.dimension != config.EMBEDDING_DIMENSION:
                raise ValueError(
                    f"Embedding dimension mismatch: provider returns {provider.dimension}, "
                    f"but config expects {config.EMBEDDING_DIMENSION}. "
                    f"Update EMBEDDING_DIMENSION in your config to match the model."
                )

            _embedding_provider = provider
        except ImportError as e:
            logger.warning(
                f"Could not load local embedding provider: {e}. Using mock provider."
            )
            _embedding_provider = MockEmbeddingProvider(
                model_id=config.EMBEDDING_MODEL_ID,
                dimension=config.EMBEDDING_DIMENSION,
            )

    return _embedding_provider

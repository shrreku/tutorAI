import asyncio
import logging
from functools import partial

from sentence_transformers import SentenceTransformer

from app.services.embedding.base import BaseEmbeddingProvider

logger = logging.getLogger(__name__)


class LocalEmbeddingProvider(BaseEmbeddingProvider):
    """Local embedding provider using sentence-transformers."""

    def __init__(self, model_id: str = "BAAI/bge-small-en-v1.5"):
        self._model_id = model_id
        logger.info(f"Loading embedding model: {model_id}")
        self.model = SentenceTransformer(model_id)
        self._dimension = self.model.get_sentence_embedding_dimension()
        logger.info(f"Embedding model loaded. Dimension: {self._dimension}")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed texts using the local model."""
        if not texts:
            return []

        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        embeddings = await loop.run_in_executor(
            None,
            partial(self.model.encode, texts, convert_to_numpy=True),
        )
        return embeddings.tolist()

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_id(self) -> str:
        return self._model_id

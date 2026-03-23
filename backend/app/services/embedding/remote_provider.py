import logging
from typing import Any, Optional

import httpx

from app.services.embedding.base import BaseEmbeddingProvider

logger = logging.getLogger(__name__)


class RemoteEmbeddingProvider(BaseEmbeddingProvider):
    """Remote embedding provider for Gemini and OpenRouter backends."""

    def __init__(
        self,
        *,
        provider: str,
        model_id: str,
        dimension: int,
        api_key: str,
        base_url: Optional[str] = None,
        timeout_seconds: float = 60.0,
    ):
        self._provider = provider.strip().lower()
        self._model_id = model_id.strip()
        self._dimension = int(dimension)
        self._api_key = api_key.strip()
        if not self._api_key:
            raise ValueError("Embedding API key is required for remote providers")

        self._base_url = self._resolve_base_url(base_url)
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    @property
    def dimension(self) -> int:
        return self._dimension

    @property
    def model_id(self) -> str:
        return self._model_id

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        if self._provider == "gemini":
            embeddings = await self._embed_gemini(texts)
        elif self._provider == "openrouter":
            embeddings = await self._embed_openrouter(texts)
        else:
            raise ValueError(f"Unsupported remote embedding provider: {self._provider}")

        self._validate_count(texts, embeddings)
        self._validate_dimensions(embeddings)
        return embeddings

    def _resolve_base_url(self, base_url: Optional[str]) -> str:
        if base_url and base_url.strip():
            return base_url.rstrip("/")
        if self._provider == "gemini":
            return "https://generativelanguage.googleapis.com/v1beta"
        if self._provider == "openrouter":
            return "https://openrouter.ai/api/v1"
        raise ValueError(f"Unsupported remote embedding provider: {self._provider}")

    def _normalize_gemini_model_name(self) -> str:
        model = self._model_id.strip()
        if model.startswith("models/"):
            return model
        if "/" in model:
            model = model.split("/")[-1]
        return f"models/{model}"

    async def _embed_gemini(self, texts: list[str]) -> list[list[float]]:
        model_name = self._normalize_gemini_model_name()
        headers = {
            "Content-Type": "application/json",
            "x-goog-api-key": self._api_key,
        }

        if len(texts) == 1:
            response = await self._client.post(
                f"{self._base_url}/{model_name}:embedContent",
                headers=headers,
                json={
                    "model": model_name,
                    "content": {"parts": [{"text": texts[0]}]},
                    "outputDimensionality": self._dimension,
                },
            )
            response.raise_for_status()
            payload = response.json()
            embedding = ((payload.get("embedding") or {}).get("values")) or []
            return [self._coerce_embedding(embedding)]

        response = await self._client.post(
            f"{self._base_url}/{model_name}:batchEmbedContents",
            headers=headers,
            json={
                "requests": [
                    {
                        "model": model_name,
                        "content": {"parts": [{"text": text}]},
                        "outputDimensionality": self._dimension,
                    }
                    for text in texts
                ]
            },
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("embeddings") or []
        return [
            self._coerce_embedding((item or {}).get("values") or []) for item in items
        ]

    async def _embed_openrouter(self, texts: list[str]) -> list[list[float]]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        response = await self._client.post(
            f"{self._base_url}/embeddings",
            headers=headers,
            json={
                "model": self._model_id,
                "input": texts if len(texts) > 1 else texts[0],
                "encoding_format": "float",
                "dimensions": self._dimension,
            },
        )
        response.raise_for_status()
        payload = response.json()
        items = payload.get("data") or []
        return [
            self._coerce_embedding((item or {}).get("embedding") or [])
            for item in items
        ]

    def _coerce_embedding(self, values: list[Any]) -> list[float]:
        return [float(value) for value in values]

    def _validate_count(self, texts: list[str], embeddings: list[list[float]]) -> None:
        if len(embeddings) != len(texts):
            raise ValueError(
                "Embedding response count mismatch from "
                f"{self._provider} provider: expected {len(texts)}, got "
                f"{len(embeddings)}"
            )

    def _validate_dimensions(self, embeddings: list[list[float]]) -> None:
        if len(embeddings) == 0:
            return
        for index, embedding in enumerate(embeddings):
            if len(embedding) != self._dimension:
                raise ValueError(
                    "Embedding dimension mismatch from "
                    f"{self._provider} provider for item {index}: expected "
                    f"{self._dimension}, got {len(embedding)}. "
                    "Update EMBEDDING_DIMENSION or choose a model/provider "
                    "configuration that supports the configured vector size."
                )

    async def aclose(self) -> None:
        await self._client.aclose()

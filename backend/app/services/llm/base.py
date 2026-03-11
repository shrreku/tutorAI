from abc import ABC, abstractmethod
from typing import Type, TypeVar, Optional
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class BaseLLMProvider(ABC):
    """Base class for LLM providers."""
    
    @abstractmethod
    async def generate(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """Generate a text response from the LLM."""
        pass
    
    @abstractmethod
    async def generate_json(
        self,
        messages: list[dict],
        schema: Type[T],
        model: str | None = None,
        temperature: float = 0.3,
        max_tokens: int = 4096,
    ) -> T:
        """Generate and parse a JSON response into a Pydantic model."""
        pass
    
    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        pass
    
    @property
    @abstractmethod
    def model_id(self) -> str:
        """Get the current model ID."""
        pass

    @property
    def total_tokens_used(self) -> dict:
        """Return cumulative token usage. Override in subclass."""
        return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

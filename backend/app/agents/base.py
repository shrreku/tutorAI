from abc import ABC, abstractmethod
from typing import TypeVar, Generic
from pydantic import BaseModel

StateT = TypeVar("StateT", bound=BaseModel)
OutputT = TypeVar("OutputT", bound=BaseModel)


class BaseAgent(ABC, Generic[StateT, OutputT]):
    """Base class for all agents in the tutoring pipeline."""

    def __init__(self, name: str):
        self.name = name

    @abstractmethod
    async def run(self, state: StateT) -> OutputT:
        """Execute the agent logic and return output."""
        pass

    @property
    @abstractmethod
    def system_prompt(self) -> str:
        """Return the system prompt for this agent."""
        pass

"""LLM port — abstract interface for AI reasoning and embedding."""

from abc import ABC, abstractmethod


class LLMPort(ABC):
    """Abstract interface for LLM operations."""

    @abstractmethod
    async def generate(self, prompt: str, system: str = "") -> str:
        """Generate text from a prompt.

        Args:
            prompt: User/context prompt.
            system: System prompt (agent identity, personality).

        Returns:
            Generated text response.
        """

    @abstractmethod
    async def embed(self, text: str) -> list[float]:
        """Generate embedding vector for text.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector (1024D float).
        """

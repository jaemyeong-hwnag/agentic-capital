"""Gemini LLM adapter — Google AI for reasoning and embedding."""

import structlog
from google import genai
from google.genai import types

from agentic_capital.config import settings
from agentic_capital.ports.llm import LLMPort

logger = structlog.get_logger()


class GeminiLLMAdapter(LLMPort):
    """Gemini LLM adapter for text generation and embedding.

    Uses Gemini 2.5 Flash for generation and text-embedding-004 for embeddings.
    """

    def __init__(
        self,
        *,
        generation_model: str = "gemini-2.5-flash-preview-05-20",
        embedding_model: str = "text-embedding-004",
        api_key: str = "",
    ) -> None:
        key = api_key or settings.gemini_api_key
        if not key:
            raise ValueError("GEMINI_API_KEY is required for GeminiLLMAdapter")

        self._client = genai.Client(api_key=key)
        self._generation_model = generation_model
        self._embedding_model = embedding_model
        logger.info(
            "gemini_adapter_initialized",
            generation_model=generation_model,
            embedding_model=embedding_model,
        )

    async def generate(self, prompt: str, system: str = "") -> str:
        """Generate text using Gemini."""
        try:
            config = types.GenerateContentConfig(
                system_instruction=system if system else None,
            )
            response = await self._client.aio.models.generate_content(
                model=self._generation_model,
                contents=prompt,
                config=config,
            )
            text = response.text or ""
            logger.debug(
                "gemini_generated",
                model=self._generation_model,
                prompt_len=len(prompt),
                response_len=len(text),
            )
            return text
        except Exception:
            logger.exception(
                "gemini_generate_failed",
                model=self._generation_model,
                prompt_len=len(prompt),
            )
            raise

    async def embed(self, text: str) -> list[float]:
        """Generate embedding using Gemini text-embedding-004."""
        try:
            result = await self._client.aio.models.embed_content(
                model=self._embedding_model,
                contents=text,
            )
            embedding = list(result.embeddings[0].values)
            logger.debug(
                "gemini_embedded",
                model=self._embedding_model,
                text_len=len(text),
                embedding_dim=len(embedding),
            )
            return embedding
        except Exception:
            logger.exception(
                "gemini_embed_failed",
                model=self._embedding_model,
                text_len=len(text),
            )
            raise

"""DeepSeek LLM adapter using its OpenAI-compatible chat API."""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from agentic_capital.adapters.llm.local_openai import (
    LocalOpenAICompatibleChatModel,
    _auth_headers,
    _extract_chat_content,
    _join_url,
)
from agentic_capital.config import settings
from agentic_capital.ports.llm import LLMPort

logger = structlog.get_logger()


def require_deepseek_api_key(api_key: str | None = None) -> str:
    """Return the configured DeepSeek API key or fail before a paid call."""
    key = api_key if api_key is not None else settings.deepseek_api_key
    if not key:
        raise ValueError("DEEPSEEK_API_KEY is required for DeepSeek provider")
    return key


class DeepSeekLLMAdapter(LLMPort):
    """LLMPort implementation for DeepSeek chat completions.

    DeepSeek is used only for reasoning. Embeddings stay on the local embedding
    path so this adapter does not introduce an extra paid embedding API.
    """

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self._base_url = base_url or settings.deepseek_base_url
        self._model = model or settings.deepseek_model
        self._api_key = require_deepseek_api_key(api_key)
        self._timeout_seconds = timeout_seconds or settings.deepseek_timeout_seconds
        self._temperature = settings.deepseek_temperature if temperature is None else temperature
        self._max_tokens = settings.deepseek_max_tokens if max_tokens is None else max_tokens
        logger.info(
            "deepseek_adapter_initialized",
            base_url=self._base_url,
            model=self._model,
        )

    @property
    def model(self) -> str:
        return self._model

    async def generate(self, prompt: str, system: str = "") -> str:
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
        }
        if self._max_tokens > 0:
            body["max_tokens"] = self._max_tokens

        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                _join_url(self._base_url, "chat/completions"),
                headers=_auth_headers(self._api_key),
                json=body,
            )
            response.raise_for_status()
            payload = response.json()
        return _extract_chat_content(payload)

    async def embed(self, text: str) -> list[float]:
        raise NotImplementedError(
            "DeepSeek provider does not provide embeddings in this project; use LOCAL_EMBEDDING_MODEL"
        )


class DeepSeekChatModel(LocalOpenAICompatibleChatModel):
    """LangChain chat model for DeepSeek's OpenAI-compatible endpoint."""

    @property
    def _llm_type(self) -> str:
        return "deepseek"

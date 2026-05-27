"""LLM provider router.

Keeps hosted and local model selection behind a small runtime boundary so
agent code can stay provider-agnostic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from agentic_capital.config import settings

logger = structlog.get_logger()

if TYPE_CHECKING:
    from agentic_capital.ports.llm import LLMPort


LOCAL_PROVIDER_NAMES = {"local", "rag", "local_openai", "domain_llm_forge"}
HOSTED_PROVIDER_NAMES = {"gemini"}


def active_llm_provider() -> str:
    return settings.llm_provider.strip().lower()


def is_local_llm_enabled() -> bool:
    return active_llm_provider() in LOCAL_PROVIDER_NAMES


def build_llm_adapter() -> LLMPort:
    """Build the core LLMPort adapter from settings."""
    if is_local_llm_enabled():
        from agentic_capital.adapters.llm.local_openai import LocalOpenAICompatibleAdapter

        return LocalOpenAICompatibleAdapter()
    if active_llm_provider() not in HOSTED_PROVIDER_NAMES:
        raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")

    from agentic_capital.adapters.llm.gemini import GeminiLLMAdapter

    return GeminiLLMAdapter()


def build_langchain_chat_model() -> Any:
    """Build a LangChain-compatible chat model from settings."""
    if is_local_llm_enabled():
        from agentic_capital.adapters.llm.local_openai import LocalOpenAICompatibleChatModel

        model = settings.local_agent_llm_model.strip()
        finance_model = settings.local_llm_model.strip()
        if not model:
            if finance_model.lower().startswith("finance_"):
                raise ValueError(
                    "LOCAL_AGENT_LLM_MODEL is required when LOCAL_LLM_MODEL points to a finance sidecar"
                )
            model = finance_model
        return LocalOpenAICompatibleChatModel(
            base_url=settings.local_llm_base_url,
            model=model,
            api_key=settings.local_llm_api_key,
            timeout_seconds=settings.local_llm_timeout_seconds,
            temperature=settings.local_llm_temperature,
            send_native_tools=settings.local_llm_send_native_tools,
        )
    if active_llm_provider() not in HOSTED_PROVIDER_NAMES:
        raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")

    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=settings.gemini_api_key,
        temperature=0.7,
    )


def llm_run_metadata() -> dict[str, Any]:
    """Return non-secret LLM metadata for reproducibility."""
    if is_local_llm_enabled():
        return {
            "llm_provider": active_llm_provider(),
            "llm_model": settings.local_llm_model,
            "agent_llm_model": settings.local_agent_llm_model,
            "embedding_model": settings.local_embedding_model,
            "llm_base_url": settings.local_llm_base_url,
        }
    return {
        "llm_provider": active_llm_provider(),
        "llm_model": "gemini-2.5-flash",
        "embedding_model": "text-embedding-004",
    }

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
HOSTED_PROVIDER_NAMES = {"deepseek", "gemini"}


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
    if active_llm_provider() == "deepseek":
        from agentic_capital.adapters.llm.deepseek import DeepSeekLLMAdapter

        return DeepSeekLLMAdapter()

    from agentic_capital.adapters.llm.gemini import GeminiLLMAdapter

    return GeminiLLMAdapter()


def build_langchain_chat_model() -> Any:
    """Build a LangChain-compatible chat model from settings."""
    if is_local_llm_enabled():
        from agentic_capital.adapters.llm.local_openai import LocalOpenAICompatibleChatModel

        model = settings.local_agent_llm_model.strip()
        finance_model = settings.local_llm_model.strip()
        agent_base_url = settings.local_agent_llm_base_url.strip()
        if not model:
            if finance_model.lower().startswith("finance_"):
                raise ValueError(
                    "LOCAL_AGENT_LLM_MODEL is required when LOCAL_LLM_MODEL points to a finance sidecar"
                )
            model = finance_model
        if finance_model.lower().startswith("finance_") and not agent_base_url:
            raise ValueError(
                "LOCAL_AGENT_LLM_BASE_URL is required when LOCAL_LLM_MODEL points to a finance sidecar"
            )
        return LocalOpenAICompatibleChatModel(
            base_url=agent_base_url or settings.local_llm_base_url,
            model=model,
            api_key=settings.local_llm_api_key,
            timeout_seconds=settings.local_agent_llm_timeout_seconds,
            temperature=settings.local_llm_temperature,
            max_tokens=settings.local_agent_llm_max_tokens,
            send_native_tools=settings.local_llm_send_native_tools,
        )
    if active_llm_provider() not in HOSTED_PROVIDER_NAMES:
        raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")
    if active_llm_provider() == "deepseek":
        from agentic_capital.adapters.llm.deepseek import DeepSeekChatModel, require_deepseek_api_key

        return DeepSeekChatModel(
            base_url=settings.deepseek_base_url,
            model=settings.deepseek_model,
            api_key=require_deepseek_api_key(),
            timeout_seconds=settings.deepseek_timeout_seconds,
            temperature=settings.deepseek_temperature,
            max_tokens=settings.deepseek_max_tokens,
            send_native_tools=settings.deepseek_send_native_tools,
        )

    from langchain_google_genai import ChatGoogleGenerativeAI

    return ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        google_api_key=settings.gemini_api_key,
        temperature=0.7,
    )


def llm_run_metadata() -> dict[str, Any]:
    """Return non-secret LLM metadata for reproducibility."""
    if is_local_llm_enabled():
        agent_model = settings.local_agent_llm_model.strip() or settings.local_llm_model
        return {
            "llm_provider": active_llm_provider(),
            "llm_model": agent_model,
            "agent_llm_model": agent_model,
            "finance_llm_model": settings.local_llm_model,
            "embedding_model": settings.local_embedding_model,
            "llm_base_url": settings.local_llm_base_url,
            "agent_llm_base_url": settings.local_agent_llm_base_url,
        }
    if active_llm_provider() == "deepseek":
        return {
            "llm_provider": active_llm_provider(),
            "llm_model": settings.deepseek_model,
            "embedding_model": settings.local_embedding_model,
            "llm_base_url": settings.deepseek_base_url,
        }
    return {
        "llm_provider": active_llm_provider(),
        "llm_model": "gemini-2.5-flash",
        "embedding_model": "text-embedding-004",
    }

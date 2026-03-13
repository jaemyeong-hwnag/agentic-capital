"""LangSmith tracing setup for LLM call monitoring.

When enabled via LANGCHAIN_TRACING_V2=true, all LangGraph workflows
and LLM calls are traced and visible in the LangSmith dashboard.
"""

from __future__ import annotations

import os

import structlog

from agentic_capital.config import settings

logger = structlog.get_logger()


def setup_tracing() -> bool:
    """Configure LangSmith tracing from settings.

    Sets environment variables that LangChain/LangGraph reads automatically.
    Returns True if tracing was enabled.
    """
    if not settings.langchain_tracing_v2 or not settings.langchain_api_key:
        logger.info("langsmith_tracing_disabled")
        return False

    os.environ["LANGCHAIN_TRACING_V2"] = "true"
    os.environ["LANGCHAIN_API_KEY"] = settings.langchain_api_key
    os.environ["LANGCHAIN_PROJECT"] = settings.langchain_project

    logger.info(
        "langsmith_tracing_enabled",
        project=settings.langchain_project,
    )
    return True

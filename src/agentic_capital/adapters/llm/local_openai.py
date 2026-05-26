"""Local OpenAI-compatible LLM adapter.

Targets llama-server and domain-llm-forge RAG Gateway endpoints without
depending on a hosted provider SDK.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import structlog
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.tools import BaseTool
from pydantic import Field

from agentic_capital.config import settings
from agentic_capital.ports.llm import LLMPort

logger = structlog.get_logger()


def _join_url(base_url: str, path: str) -> str:
    """Join OpenAI-compatible base URLs safely."""
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _auth_headers(api_key: str) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _extract_chat_content(payload: dict[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"].get("content", "")
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Local LLM response missing choices[0].message.content") from exc
    return content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)


def _extract_embedding(payload: dict[str, Any]) -> list[float]:
    try:
        vector = payload["data"][0]["embedding"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Local embedding response missing data[0].embedding") from exc
    if not isinstance(vector, list):
        raise ValueError("Local embedding response is not a vector")
    return [float(v) for v in vector]


def _message_to_openai(message: BaseMessage) -> dict[str, Any]:
    content = message.content
    if isinstance(message, SystemMessage):
        role = "system"
    elif isinstance(message, HumanMessage):
        role = "user"
    elif isinstance(message, ToolMessage):
        result: dict[str, Any] = {
            "role": "tool",
            "content": content,
            "tool_call_id": message.tool_call_id,
        }
        return result
    else:
        role = "assistant"

    result = {"role": role, "content": content}
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        result["tool_calls"] = [
            {
                "id": tc.get("id"),
                "type": "function",
                "function": {
                    "name": tc.get("name"),
                    "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False),
                },
            }
            for tc in tool_calls
        ]
    return result


def _tool_to_openai_schema(tool: Any) -> dict[str, Any]:
    """Convert a LangChain tool-like object to OpenAI function schema."""
    if isinstance(tool, dict):
        return tool

    name = getattr(tool, "name", None) or getattr(tool, "__name__", "tool")
    description = getattr(tool, "description", "") or ""
    args_schema = getattr(tool, "args_schema", None)
    if args_schema is not None and hasattr(args_schema, "model_json_schema"):
        parameters = args_schema.model_json_schema()
    elif isinstance(tool, BaseTool) and getattr(tool, "args", None):
        properties = {
            key: {"title": key, "type": value.get("type", "string")}
            for key, value in tool.args.items()
        }
        parameters = {"type": "object", "properties": properties}
    else:
        parameters = {"type": "object", "properties": {}}

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": parameters,
        },
    }


def _parse_tool_calls(raw_tool_calls: Any) -> list[dict[str, Any]]:
    parsed: list[dict[str, Any]] = []
    if not isinstance(raw_tool_calls, list):
        return parsed

    for index, raw in enumerate(raw_tool_calls):
        function = raw.get("function", {}) if isinstance(raw, dict) else {}
        name = function.get("name") or raw.get("name") if isinstance(raw, dict) else ""
        arguments = function.get("arguments") or raw.get("arguments") if isinstance(raw, dict) else {}
        if isinstance(arguments, str):
            try:
                args = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                args = {"_raw_arguments": arguments}
        elif isinstance(arguments, dict):
            args = arguments
        else:
            args = {}
        parsed.append({
            "name": name or "",
            "args": args,
            "id": raw.get("id") or f"local_call_{index}",
        })
    return parsed


def _chat_result_from_payload(payload: dict[str, Any]) -> ChatResult:
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Local LLM response missing choices[0].message") from exc

    content = message.get("content") or ""
    tool_calls = _parse_tool_calls(message.get("tool_calls"))
    ai_message = AIMessage(content=content, tool_calls=tool_calls)
    return ChatResult(generations=[ChatGeneration(message=ai_message)])


class LocalOpenAICompatibleAdapter(LLMPort):
    """LLMPort implementation for local OpenAI-compatible servers."""

    def __init__(
        self,
        *,
        base_url: str | None = None,
        model: str | None = None,
        embedding_model: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float | None = None,
        temperature: float | None = None,
    ) -> None:
        self._base_url = base_url or settings.local_llm_base_url
        self._model = model or settings.local_llm_model
        self._embedding_model = embedding_model or settings.local_embedding_model
        self._api_key = api_key if api_key is not None else settings.local_llm_api_key
        self._timeout_seconds = timeout_seconds or settings.local_llm_timeout_seconds
        self._temperature = settings.local_llm_temperature if temperature is None else temperature
        logger.info(
            "local_llm_adapter_initialized",
            base_url=self._base_url,
            model=self._model,
            embedding_model=self._embedding_model,
        )

    @property
    def model(self) -> str:
        return self._model

    @property
    def embedding_model(self) -> str:
        return self._embedding_model

    async def generate(self, prompt: str, system: str = "") -> str:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body = {
            "model": self._model,
            "messages": messages,
            "temperature": self._temperature,
        }
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
        body = {"model": self._embedding_model, "input": text}
        async with httpx.AsyncClient(timeout=self._timeout_seconds) as client:
            response = await client.post(
                _join_url(self._base_url, "embeddings"),
                headers=_auth_headers(self._api_key),
                json=body,
            )
            response.raise_for_status()
            payload = response.json()
        return _extract_embedding(payload)


class LocalOpenAICompatibleChatModel(BaseChatModel):
    """LangChain chat model for local OpenAI-compatible endpoints."""

    base_url: str
    model: str
    api_key: str = ""
    timeout_seconds: float = 30.0
    temperature: float = 0.2
    bound_tools: list[Any] = Field(default_factory=list)
    tool_choice: str | None = None

    @property
    def _llm_type(self) -> str:
        return "local-openai-compatible"

    def bind_tools(
        self,
        tools: list[Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> "LocalOpenAICompatibleChatModel":
        return self.model_copy(update={
            "bound_tools": list(tools),
            "tool_choice": tool_choice or kwargs.get("tool_choice"),
        })

    def _body(self, messages: list[BaseMessage], stop: list[str] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": [_message_to_openai(message) for message in messages],
            "temperature": self.temperature,
        }
        if stop:
            body["stop"] = stop
        if self.bound_tools:
            body["tools"] = [_tool_to_openai_schema(tool) for tool in self.bound_tools]
            body["tool_choice"] = self.tool_choice or "auto"
        return body

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        with httpx.Client(timeout=self.timeout_seconds) as client:
            response = client.post(
                _join_url(self.base_url, "chat/completions"),
                headers=_auth_headers(self.api_key),
                json=self._body(messages, stop),
            )
            response.raise_for_status()
            payload = response.json()
        return _chat_result_from_payload(payload)

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                _join_url(self.base_url, "chat/completions"),
                headers=_auth_headers(self.api_key),
                json=self._body(messages, stop),
            )
            response.raise_for_status()
            payload = response.json()
        return _chat_result_from_payload(payload)

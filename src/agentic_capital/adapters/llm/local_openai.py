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
        name = function.get("name") or raw.get("name") or raw.get("tool") if isinstance(raw, dict) else ""
        arguments = (
            function.get("arguments") or raw.get("arguments") or raw.get("args")
            if isinstance(raw, dict)
            else {}
        )
        if isinstance(arguments, str):
            try:
                args = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                args = {"_raw_arguments": arguments}
        elif isinstance(arguments, dict):
            args = _normalize_tool_args(arguments)
        else:
            args = {}
        parsed.append({
            "name": name or "",
            "args": args,
            "id": raw.get("id") or f"local_call_{index}",
        })
    return parsed


def _looks_like_json_schema_properties(value: dict[str, Any]) -> bool:
    """Return true for OpenAI schema property maps, not runtime tool args."""
    if not value:
        return False
    for nested in value.values():
        if not isinstance(nested, dict):
            return False
        if any(key in nested for key in ("type", "anyOf", "oneOf", "allOf", "enum", "description", "title")):
            continue
        return False
    return True


def _normalize_tool_args(args: dict[str, Any]) -> dict[str, Any]:
    """Repair common local-model tool-call argument wrappers.

    Some local instruct models echo the compact schema wrapper as
    {"properties": {"symbol": "005930"}} instead of the actual runtime args.
    Unwrap only when the nested object is value-like rather than a JSON schema.
    """
    if set(args) == {"properties"} and isinstance(args.get("properties"), dict):
        properties = args["properties"]
        if not _looks_like_json_schema_properties(properties):
            return properties
    return args


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = [line for line in stripped.splitlines() if not line.strip().startswith("```")]
        stripped = "\n".join(lines).strip()
    return stripped


def _extract_json_value(text: str) -> Any | None:
    stripped = _strip_code_fence(text)
    if stripped.lower().startswith("_tool_calls="):
        stripped = stripped.split("=", 1)[1].strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        object_start = stripped.find("{")
        array_start = stripped.find("[")
        starts = [idx for idx in (object_start, array_start) if idx >= 0]
        if not starts:
            return None
        start = min(starts)
        end = max(stripped.rfind("}"), stripped.rfind("]"))
        if start < 0 or end <= start:
            return None
        try:
            return json.loads(stripped[start:end + 1])
        except json.JSONDecodeError:
            return None


def _extract_json_object(text: str) -> dict[str, Any] | None:
    parsed = _extract_json_value(text)
    return parsed if isinstance(parsed, dict) else None


def _parse_tool_calls_from_content(content: str) -> list[dict[str, Any]]:
    parsed = _extract_json_value(content)
    if not parsed:
        return []
    if isinstance(parsed, list):
        raw_tool_calls = parsed
    elif isinstance(parsed, dict):
        raw_tool_calls = parsed.get("tool_calls")
        if raw_tool_calls is None and parsed.get("tool_call"):
            raw_tool_calls = [parsed["tool_call"]]
        if raw_tool_calls is None and any(parsed.get(key) for key in ("name", "tool", "function")):
            raw_tool_calls = [parsed]
    else:
        raw_tool_calls = None
    return _parse_tool_calls(raw_tool_calls)


def _shorten(value: str, limit: int = 160) -> str:
    compact = " ".join(value.split())
    return compact if len(compact) <= limit else f"{compact[:limit].rstrip()}..."


def _compact_parameters(parameters: dict[str, Any]) -> dict[str, Any]:
    properties = parameters.get("properties")
    if not isinstance(properties, dict):
        return {"args": []}

    compact_properties: dict[str, dict[str, Any]] = {}
    for name, schema in properties.items():
        if not isinstance(schema, dict):
            compact_properties[name] = {"type": "any"}
            continue
        entry: dict[str, Any] = {"type": schema.get("type") or schema.get("anyOf", "any")}
        if "enum" in schema:
            entry["enum"] = schema["enum"]
        compact_properties[name] = entry

    compact: dict[str, Any] = {"properties": compact_properties}
    required = parameters.get("required")
    if isinstance(required, list) and required:
        compact["required"] = required
    return compact


def _chat_result_from_payload(payload: dict[str, Any]) -> ChatResult:
    try:
        message = payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Local LLM response missing choices[0].message") from exc

    content = message.get("content") or ""
    tool_calls = _parse_tool_calls(message.get("tool_calls"))
    if not tool_calls and isinstance(content, str):
        tool_calls = _parse_tool_calls_from_content(content)
        if tool_calls:
            content = ""
    ai_message = AIMessage(content=content, tool_calls=tool_calls)
    return ChatResult(generations=[ChatGeneration(message=ai_message)])


def _tool_prompt(tools: list[Any]) -> str:
    schemas = [_tool_to_openai_schema(tool) for tool in tools]
    compact = [
        {
            "name": schema.get("function", {}).get("name", ""),
            "description": _shorten(schema.get("function", {}).get("description", "")),
            "parameters": _compact_parameters(schema.get("function", {}).get("parameters", {})),
        }
        for schema in schemas
    ]
    return (
        "도구 호출이 필요하면 일반 답변 대신 JSON object만 출력하세요. "
        "형식: {\"tool_calls\":[{\"name\":\"tool_name\",\"args\":{},\"id\":\"call_1\"}]}. "
        "필요한 도구가 없거나 최종 답변이면 일반 텍스트로 답하고, 최종 TRADER_TASK에는 JSON tool call을 넣지 마세요. "
        f"사용 가능한 도구: {json.dumps(compact, ensure_ascii=False)}"
    )


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
    max_tokens: int = 512
    send_native_tools: bool = False
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
        openai_messages = [_message_to_openai(message) for message in messages]
        if self.bound_tools:
            tool_instruction = _tool_prompt(self.bound_tools)
            if openai_messages and openai_messages[0].get("role") == "system":
                openai_messages[0]["content"] = f"{openai_messages[0].get('content', '')}\n\n{tool_instruction}"
            else:
                openai_messages.insert(0, {"role": "system", "content": tool_instruction})

        body: dict[str, Any] = {
            "model": self.model,
            "messages": openai_messages,
            "temperature": self.temperature,
        }
        if self.max_tokens > 0:
            body["max_tokens"] = self.max_tokens
        if stop:
            body["stop"] = stop
        if self.bound_tools and self.send_native_tools:
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

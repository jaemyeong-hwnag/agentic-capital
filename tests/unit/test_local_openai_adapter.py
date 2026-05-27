"""Tests for local OpenAI-compatible LLM adapters."""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from agentic_capital.adapters.llm.local_openai import (
    LocalOpenAICompatibleAdapter,
    LocalOpenAICompatibleChatModel,
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeAsyncClient:
    last_request = {}

    def __init__(self, *, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return None

    async def post(self, url, *, headers, json):
        _FakeAsyncClient.last_request = {"url": url, "headers": headers, "json": json}
        if url.endswith("/embeddings"):
            return _FakeResponse({"data": [{"embedding": [0.1, 0.2, 0.3]}]})
        return _FakeResponse({"choices": [{"message": {"content": "local answer"}}]})


class _FakeSyncClient:
    last_request = {}

    def __init__(self, *, timeout):
        self.timeout = timeout

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return None

    def post(self, url, *, headers, json):
        _FakeSyncClient.last_request = {"url": url, "headers": headers, "json": json}
        return _FakeResponse({
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{
                        "id": "call_1",
                        "type": "function",
                        "function": {
                            "name": "get_balance",
                            "arguments": '{"market": "kr_stock"}',
                        },
                    }],
                },
            }],
        })


@pytest.mark.asyncio
async def test_local_adapter_generate_posts_chat_completion(monkeypatch):
    monkeypatch.setattr("agentic_capital.adapters.llm.local_openai.httpx.AsyncClient", _FakeAsyncClient)
    adapter = LocalOpenAICompatibleAdapter(
        base_url="http://127.0.0.1:8080/v1/",
        model="finance_decision_model",
        embedding_model="finance_embedding_model",
        api_key="",
        timeout_seconds=5,
    )

    result = await adapter.generate("005930 매수 가능?", system="paper mode only")

    assert result == "local answer"
    assert _FakeAsyncClient.last_request["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    assert _FakeAsyncClient.last_request["json"]["model"] == "finance_decision_model"
    assert _FakeAsyncClient.last_request["json"]["messages"][0]["role"] == "system"
    assert "Authorization" not in _FakeAsyncClient.last_request["headers"]


@pytest.mark.asyncio
async def test_local_adapter_embed_posts_embedding_request(monkeypatch):
    monkeypatch.setattr("agentic_capital.adapters.llm.local_openai.httpx.AsyncClient", _FakeAsyncClient)
    adapter = LocalOpenAICompatibleAdapter(
        base_url="http://127.0.0.1:8080/v1",
        model="finance_decision_model",
        embedding_model="finance_embedding_model",
        timeout_seconds=5,
    )

    result = await adapter.embed("risk limit evidence")

    assert result == [0.1, 0.2, 0.3]
    assert _FakeAsyncClient.last_request["url"] == "http://127.0.0.1:8080/v1/embeddings"
    assert _FakeAsyncClient.last_request["json"]["model"] == "finance_embedding_model"


def test_local_chat_model_parses_tool_calls(monkeypatch):
    monkeypatch.setattr("agentic_capital.adapters.llm.local_openai.httpx.Client", _FakeSyncClient)
    model = LocalOpenAICompatibleChatModel(
        base_url="http://127.0.0.1:8080/v1",
        model="finance_tool_planner_model",
        timeout_seconds=5,
    ).bind_tools([
        {
            "type": "function",
            "function": {
                "name": "get_balance",
                "description": "paper account balance",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ])

    message = model.invoke([HumanMessage(content="잔고 확인")])

    assert message.tool_calls[0]["name"] == "get_balance"
    assert message.tool_calls[0]["args"] == {"market": "kr_stock"}
    assert "tools" not in _FakeSyncClient.last_request["json"]
    assert "tool_choice" not in _FakeSyncClient.last_request["json"]
    assert "tool_calls" in _FakeSyncClient.last_request["json"]["messages"][0]["content"]


def test_local_chat_model_can_opt_into_native_tool_payload(monkeypatch):
    monkeypatch.setattr("agentic_capital.adapters.llm.local_openai.httpx.Client", _FakeSyncClient)
    model = LocalOpenAICompatibleChatModel(
        base_url="http://127.0.0.1:8080/v1",
        model="finance_tool_planner_model",
        timeout_seconds=5,
        send_native_tools=True,
    ).bind_tools([
        {
            "type": "function",
            "function": {
                "name": "get_balance",
                "description": "paper account balance",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    ])

    model.invoke([HumanMessage(content="잔고 확인")])

    assert _FakeSyncClient.last_request["json"]["tool_choice"] == "auto"
    assert _FakeSyncClient.last_request["json"]["tools"][0]["function"]["name"] == "get_balance"


def test_local_chat_model_parses_textual_tool_call(monkeypatch):
    class _TextToolClient(_FakeSyncClient):
        def post(self, url, *, headers, json):
            return _FakeResponse({
                "choices": [{
                    "message": {
                        "content": '{"tool_calls":[{"name":"get_positions","args":{"market":"kr_stock"},"id":"call_2"}]}',
                    },
                }],
            })

    monkeypatch.setattr("agentic_capital.adapters.llm.local_openai.httpx.Client", _TextToolClient)
    model = LocalOpenAICompatibleChatModel(
        base_url="http://127.0.0.1:18000/v1",
        model="finance_decision_model",
        timeout_seconds=5,
    ).bind_tools([
        {
            "type": "function",
            "function": {
                "name": "get_positions",
                "description": "paper positions",
                "parameters": {"type": "object", "properties": {"market": {"type": "string"}}},
            },
        },
    ])

    message = model.invoke([HumanMessage(content="포지션 확인")])

    assert message.content == ""
    assert message.tool_calls[0]["name"] == "get_positions"
    assert message.tool_calls[0]["args"] == {"market": "kr_stock"}


def test_local_chat_model_repairs_properties_wrapped_tool_args(monkeypatch):
    class _PropertiesWrappedClient(_FakeSyncClient):
        def post(self, url, *, headers, json):
            return _FakeResponse({
                "choices": [{
                    "message": {
                        "content": (
                            '{"tool_calls":[{"name":"get_quote",'
                            '"args":{"properties":{"symbol":"005930"}},"id":"call_3"}]}'
                        ),
                    },
                }],
            })

    monkeypatch.setattr("agentic_capital.adapters.llm.local_openai.httpx.Client", _PropertiesWrappedClient)
    model = LocalOpenAICompatibleChatModel(
        base_url="http://127.0.0.1:19000/v1",
        model="agentic_capital_react_model",
        timeout_seconds=5,
    ).bind_tools([
        {
            "type": "function",
            "function": {
                "name": "get_quote",
                "description": "paper quote",
                "parameters": {
                    "type": "object",
                    "properties": {"symbol": {"type": "string"}},
                    "required": ["symbol"],
                },
            },
        },
    ])

    message = model.invoke([HumanMessage(content="005930 quote")])

    assert message.tool_calls[0]["name"] == "get_quote"
    assert message.tool_calls[0]["args"] == {"symbol": "005930"}

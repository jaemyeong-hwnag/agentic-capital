"""Unit tests for DeepSeek LLM adapters."""

from __future__ import annotations

import pytest
from langchain_core.messages import HumanMessage

from agentic_capital.adapters.llm.deepseek import DeepSeekChatModel, DeepSeekLLMAdapter


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
        return _FakeResponse({"choices": [{"message": {"content": "deepseek answer"}}]})


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
        return _FakeResponse({"choices": [{"message": {"content": "operating note"}}]})


def test_deepseek_adapter_requires_api_key() -> None:
    with pytest.raises(ValueError, match="DEEPSEEK_API_KEY"):
        DeepSeekLLMAdapter(api_key="")


@pytest.mark.asyncio
async def test_deepseek_adapter_generate_posts_chat_completion(monkeypatch) -> None:
    monkeypatch.setattr("agentic_capital.adapters.llm.deepseek.httpx.AsyncClient", _FakeAsyncClient)
    adapter = DeepSeekLLMAdapter(
        base_url="https://api.deepseek.com/v1/",
        model="deepseek-v4-flash",
        api_key="test-deepseek-key",
        timeout_seconds=5,
        max_tokens=256,
    )

    result = await adapter.generate("make money", system="paper mode only")

    assert result == "deepseek answer"
    assert _FakeAsyncClient.last_request["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert _FakeAsyncClient.last_request["headers"]["Authorization"] == "Bearer test-deepseek-key"
    assert _FakeAsyncClient.last_request["json"]["model"] == "deepseek-v4-flash"
    assert _FakeAsyncClient.last_request["json"]["max_tokens"] == 256


@pytest.mark.asyncio
async def test_deepseek_adapter_does_not_add_paid_embedding_api() -> None:
    adapter = DeepSeekLLMAdapter(api_key="test-deepseek-key")

    with pytest.raises(NotImplementedError, match="LOCAL_EMBEDDING_MODEL"):
        await adapter.embed("memory text")


def test_deepseek_chat_model_uses_openai_compatible_endpoint(monkeypatch) -> None:
    monkeypatch.setattr("agentic_capital.adapters.llm.local_openai.httpx.Client", _FakeSyncClient)
    model = DeepSeekChatModel(
        base_url="https://api.deepseek.com/v1",
        model="deepseek-v4-flash",
        api_key="test-deepseek-key",
        timeout_seconds=5,
        max_tokens=128,
    )

    message = model.invoke([HumanMessage(content="cycle:1")])

    assert message.content == "operating note"
    assert _FakeSyncClient.last_request["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert _FakeSyncClient.last_request["headers"]["Authorization"] == "Bearer test-deepseek-key"
    assert _FakeSyncClient.last_request["json"]["model"] == "deepseek-v4-flash"
    assert _FakeSyncClient.last_request["json"]["max_tokens"] == 128

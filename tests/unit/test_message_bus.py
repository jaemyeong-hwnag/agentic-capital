"""Unit tests for Redis Stream message bus."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agentic_capital.core.communication.bus import MessageBus
from agentic_capital.core.communication.protocol import AgentMessage, MessageType
from agentic_capital.core.communication.serializer import serialize_message


def _make_message(
    msg_type: MessageType = MessageType.SIGNAL,
    sender_id=None,
    receiver_id=None,
) -> AgentMessage:
    return AgentMessage(
        type=msg_type,
        sender_id=sender_id or uuid4(),
        receiver_id=receiver_id,
        priority=0.8,
        content={"signal": "BUY", "symbol": "005930", "confidence": 0.75},
    )


def _make_redis():
    redis = MagicMock()
    redis.xgroup_create = AsyncMock()
    redis.xadd = AsyncMock(return_value="1234-0")
    redis.xreadgroup = AsyncMock(return_value=[])
    redis.xack = AsyncMock()
    redis.xlen = AsyncMock(return_value=0)
    redis.xtrim = AsyncMock()
    redis.delete = AsyncMock()
    return redis


class TestMessageBus:
    def test_create(self):
        bus = MessageBus(_make_redis())
        assert bus._initialized is False

    @pytest.mark.asyncio
    async def test_initialize_creates_group(self):
        redis = _make_redis()
        bus = MessageBus(redis)
        await bus.initialize()
        redis.xgroup_create.assert_called_once()
        assert bus._initialized is True

    @pytest.mark.asyncio
    async def test_initialize_idempotent(self):
        redis = _make_redis()
        bus = MessageBus(redis)
        await bus.initialize()
        await bus.initialize()
        # Should only call xgroup_create once
        redis.xgroup_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_handles_busygroup(self):
        import redis.asyncio as aioredis
        redis = _make_redis()
        redis.xgroup_create = AsyncMock(side_effect=aioredis.ResponseError("BUSYGROUP already exists"))
        bus = MessageBus(redis)
        await bus.initialize()  # Should not raise
        assert bus._initialized is True

    @pytest.mark.asyncio
    async def test_publish(self):
        redis = _make_redis()
        bus = MessageBus(redis)
        msg = _make_message()
        entry_id = await bus.publish(msg)
        assert entry_id == "1234-0"
        redis.xadd.assert_called_once()

    @pytest.mark.asyncio
    async def test_publish_includes_metadata(self):
        redis = _make_redis()
        bus = MessageBus(redis)
        msg = _make_message(msg_type=MessageType.PLAN)
        await bus.publish(msg)
        call_args = redis.xadd.call_args
        fields = call_args[0][1]
        assert fields["type"] == "PLAN"
        assert fields["sender"] == str(msg.sender_id)

    @pytest.mark.asyncio
    async def test_consume_no_messages(self):
        redis = _make_redis()
        bus = MessageBus(redis)
        messages = await bus.consume("agent-1")
        assert messages == []

    @pytest.mark.asyncio
    async def test_consume_with_messages(self):
        redis = _make_redis()
        msg = _make_message()
        payload = serialize_message(msg)

        redis.xreadgroup = AsyncMock(return_value=[
            ("agent:messages", [("1234-0", {"data": payload, "sender": str(msg.sender_id), "type": msg.type})])
        ])

        bus = MessageBus(redis)
        messages = await bus.consume("agent-1")
        assert len(messages) == 1
        assert messages[0].type == MessageType.SIGNAL
        redis.xack.assert_called_once()

    @pytest.mark.asyncio
    async def test_consume_for_agent_filters_broadcast(self):
        redis = _make_redis()
        agent_id = uuid4()

        # Broadcast message (receiver_id=None)
        broadcast_msg = _make_message(receiver_id=None)
        # Targeted message for our agent
        targeted_msg = _make_message(receiver_id=agent_id)
        # Message for someone else
        other_msg = _make_message(receiver_id=uuid4())

        payloads = [serialize_message(m) for m in [broadcast_msg, targeted_msg, other_msg]]
        redis.xreadgroup = AsyncMock(return_value=[
            ("agent:messages", [
                ("1-0", {"data": payloads[0], "sender": "x", "type": "SIGNAL"}),
                ("2-0", {"data": payloads[1], "sender": "x", "type": "SIGNAL"}),
                ("3-0", {"data": payloads[2], "sender": "x", "type": "SIGNAL"}),
            ])
        ])

        bus = MessageBus(redis)
        messages = await bus.consume_for_agent(agent_id)
        # Should get broadcast + targeted, not the other agent's message
        assert len(messages) == 2

    @pytest.mark.asyncio
    async def test_stream_length(self):
        redis = _make_redis()
        redis.xlen = AsyncMock(return_value=42)
        bus = MessageBus(redis)
        length = await bus.stream_length()
        assert length == 42

    @pytest.mark.asyncio
    async def test_trim(self):
        redis = _make_redis()
        bus = MessageBus(redis)
        await bus.trim(500)
        redis.xtrim.assert_called_once()

    @pytest.mark.asyncio
    async def test_clear(self):
        redis = _make_redis()
        bus = MessageBus(redis)
        await bus.initialize()
        assert bus._initialized is True
        await bus.clear()
        assert bus._initialized is False
        redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_consume_handles_response_error(self):
        import redis.asyncio as aioredis
        redis = _make_redis()
        redis.xreadgroup = AsyncMock(side_effect=aioredis.ResponseError("NOGROUP"))
        bus = MessageBus(redis)
        messages = await bus.consume("agent-1")
        assert messages == []

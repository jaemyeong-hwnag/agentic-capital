"""Tests for LACP communication protocol and serialization."""

from uuid import uuid4

from agentic_capital.core.communication.protocol import AgentMessage, MessageType
from agentic_capital.core.communication.serializer import deserialize_message, serialize_message


class TestAgentMessage:
    def test_create_signal(self) -> None:
        msg = AgentMessage(
            type=MessageType.SIGNAL,
            sender_id=uuid4(),
            content={"signal": "BUY", "ticker": "AAPL", "confidence": 0.72},
        )
        assert msg.type == MessageType.SIGNAL
        assert msg.content["signal"] == "BUY"
        assert msg.ttl == 3

    def test_broadcast_message(self) -> None:
        msg = AgentMessage(
            type=MessageType.OBSERVE,
            sender_id=uuid4(),
            receiver_id=None,
            content={"observation": "Market volatility increased"},
        )
        assert msg.receiver_id is None


class TestSerialization:
    def test_roundtrip(self) -> None:
        original = AgentMessage(
            type=MessageType.PLAN,
            sender_id=uuid4(),
            receiver_id=uuid4(),
            priority=0.85,
            content={"thesis": "Focus on tech sector"},
        )
        packed = serialize_message(original)
        assert isinstance(packed, bytes)

        restored = deserialize_message(packed)
        assert restored.type == original.type
        assert restored.priority == original.priority
        assert restored.content["thesis"] == "Focus on tech sector"

    def test_msgpack_smaller_than_json(self) -> None:
        msg = AgentMessage(
            type=MessageType.SIGNAL,
            sender_id=uuid4(),
            content={"signal": "BUY", "ticker": "AAPL", "confidence": 0.72},
        )
        packed = serialize_message(msg)
        json_size = len(msg.model_dump_json().encode())
        # MessagePack should be smaller than JSON
        assert len(packed) < json_size

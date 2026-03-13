"""MessagePack serialization for agent-to-agent communication."""

import msgpack
import orjson

from agentic_capital.core.communication.protocol import AgentMessage


def serialize_message(message: AgentMessage) -> bytes:
    """Serialize an AgentMessage to MessagePack bytes."""
    data = orjson.loads(message.model_dump_json())
    return msgpack.packb(data, use_bin_type=True)


def deserialize_message(data: bytes) -> AgentMessage:
    """Deserialize MessagePack bytes to an AgentMessage."""
    unpacked = msgpack.unpackb(data, raw=False)
    return AgentMessage.model_validate(unpacked)

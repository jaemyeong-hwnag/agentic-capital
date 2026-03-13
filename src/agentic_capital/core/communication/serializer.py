"""MessagePack serialization for agent-to-agent communication."""

import structlog
import msgpack
import orjson

from agentic_capital.core.communication.protocol import AgentMessage

logger = structlog.get_logger()


def serialize_message(message: AgentMessage) -> bytes:
    """Serialize an AgentMessage to MessagePack bytes."""
    try:
        data = orjson.loads(message.model_dump_json())
        return msgpack.packb(data, use_bin_type=True)
    except Exception:
        logger.exception("serialize_message_failed", message_type=message.type)
        raise


def deserialize_message(data: bytes) -> AgentMessage:
    """Deserialize MessagePack bytes to an AgentMessage."""
    try:
        unpacked = msgpack.unpackb(data, raw=False)
        return AgentMessage.model_validate(unpacked)
    except Exception:
        logger.exception("deserialize_message_failed", data_len=len(data))
        raise

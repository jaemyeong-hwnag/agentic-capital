"""Message bus — Redis Stream-based agent communication.

Agents publish LACP messages (PLAN/ACT/OBSERVE/SIGNAL) to Redis Streams.
Each agent has its own consumer within a consumer group, ensuring
messages are processed exactly once.
"""

from __future__ import annotations

from uuid import UUID

import structlog
import redis.asyncio as aioredis

from agentic_capital.core.communication.protocol import AgentMessage
from agentic_capital.core.communication.serializer import deserialize_message, serialize_message

logger = structlog.get_logger()

# Stream key pattern
_STREAM_KEY = "agent:messages"
_GROUP_NAME = "agents"


class MessageBus:
    """Redis Stream-based message bus for agent communication.

    Supports:
    - Publishing messages to a shared stream
    - Per-agent consumption via consumer groups
    - Broadcast and targeted messages
    - TTL-based message expiration (via stream trimming)
    """

    def __init__(self, redis: aioredis.Redis, *, stream_key: str = _STREAM_KEY) -> None:  # type: ignore[type-arg]
        self._redis = redis
        self._stream_key = stream_key
        self._group_name = _GROUP_NAME
        self._initialized = False

    async def initialize(self) -> None:
        """Create the consumer group if it doesn't exist."""
        if self._initialized:
            return
        try:
            await self._redis.xgroup_create(
                self._stream_key, self._group_name, id="0", mkstream=True
            )
            logger.info("message_bus_initialized", stream=self._stream_key)
        except aioredis.ResponseError as e:
            if "BUSYGROUP" in str(e):
                # Group already exists
                pass
            else:
                raise
        self._initialized = True

    async def publish(self, message: AgentMessage, *, max_len: int = 10000) -> str:
        """Publish a message to the stream.

        Args:
            message: LACP message to publish.
            max_len: Approximate max stream length (auto-trim).

        Returns:
            Stream entry ID.
        """
        await self.initialize()
        payload = serialize_message(message)
        entry_id = await self._redis.xadd(
            self._stream_key,
            {"data": payload, "sender": str(message.sender_id), "type": message.type},
            maxlen=max_len,
            approximate=True,
        )
        logger.debug(
            "message_published",
            type=message.type,
            sender=str(message.sender_id),
            receiver=str(message.receiver_id) if message.receiver_id else "broadcast",
            entry_id=entry_id,
        )
        return entry_id

    async def consume(
        self,
        consumer_name: str,
        *,
        count: int = 10,
        block_ms: int = 0,
    ) -> list[AgentMessage]:
        """Consume messages from the stream for a specific agent.

        Args:
            consumer_name: Unique consumer name (typically agent ID).
            count: Max messages to read per call.
            block_ms: Block for N ms waiting for new messages (0 = no block).

        Returns:
            List of AgentMessage objects.
        """
        await self.initialize()
        try:
            results = await self._redis.xreadgroup(
                self._group_name,
                consumer_name,
                {self._stream_key: ">"},
                count=count,
                block=block_ms if block_ms > 0 else None,
            )
        except aioredis.ResponseError:
            logger.warning("consume_failed_group_not_ready", consumer=consumer_name)
            return []

        messages = []
        if not results:
            return messages

        for _stream, entries in results:
            for entry_id, fields in entries:
                try:
                    data = fields.get("data") or fields.get(b"data")
                    if data is None:
                        continue
                    if isinstance(data, str):
                        data = data.encode("latin-1")
                    msg = deserialize_message(data)
                    messages.append(msg)
                    # Acknowledge the message
                    await self._redis.xack(self._stream_key, self._group_name, entry_id)
                except Exception:
                    logger.exception("message_deserialize_failed", entry_id=entry_id)

        if messages:
            logger.debug("messages_consumed", consumer=consumer_name, count=len(messages))
        return messages

    async def consume_for_agent(
        self,
        agent_id: UUID,
        *,
        count: int = 10,
        block_ms: int = 0,
    ) -> list[AgentMessage]:
        """Consume messages targeted at a specific agent (or broadcast).

        Filters messages: only returns those addressed to this agent or broadcast.
        """
        all_messages = await self.consume(
            consumer_name=str(agent_id), count=count, block_ms=block_ms
        )
        return [
            msg for msg in all_messages
            if msg.receiver_id is None or msg.receiver_id == agent_id
        ]

    async def stream_length(self) -> int:
        """Get the current stream length."""
        return await self._redis.xlen(self._stream_key)

    async def trim(self, max_len: int = 1000) -> None:
        """Trim the stream to approximately max_len entries."""
        await self._redis.xtrim(self._stream_key, maxlen=max_len, approximate=True)

    async def clear(self) -> None:
        """Delete the entire stream (for testing/reset)."""
        await self._redis.delete(self._stream_key)
        self._initialized = False

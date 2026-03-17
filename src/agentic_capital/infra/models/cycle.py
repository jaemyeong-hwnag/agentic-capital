"""AgentCycleModel — full LLM activity trace per agent cycle.

Records everything the AI did in a cycle:
- Tool call sequence with inputs/outputs (compact format)
- Final LLM reasoning text
- Cycle timing and metadata
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from agentic_capital.infra.models.base import Base


class AgentCycleModel(Base):
    """agent_cycles — complete per-cycle activity record.

    tool_sequence: compact list of tool calls this cycle:
      [{"t": "get_balance", "in": "", "out": "tot:1499883,avl:39366,ccy:KRW"},
       {"t": "submit_order", "in": "sym:069500,sd:buy,qty:1", "out": "oid:xxx,st:submitted,fee:13"}]

    llm_reasoning: final AI response text (last AIMessage content).
    """

    __tablename__ = "agent_cycles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    simulation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    cycle_number: Mapped[int] = mapped_column(Integer, nullable=False)

    # Full tool call chain — compact JSON (AI-friendly TOON/compact format)
    tool_sequence: Mapped[list] = mapped_column(JSONB, default=list)

    # Final AI response text — the reasoning/conclusion
    llm_reasoning: Mapped[str] = mapped_column(Text, default="")

    # Emotion state at start of cycle (VAD+ snapshot)
    emotion_snapshot: Mapped[dict] = mapped_column(JSONB, default=dict)

    # Timing
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Summary counts
    tool_calls_count: Mapped[int] = mapped_column(Integer, default=0)
    decisions_count: Mapped[int] = mapped_column(Integer, default=0)
    errors_count: Mapped[int] = mapped_column(Integer, default=0)
    next_cycle_seconds: Mapped[float] = mapped_column(Float, default=0)

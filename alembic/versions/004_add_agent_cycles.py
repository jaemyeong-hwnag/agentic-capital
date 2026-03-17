"""Add agent_cycles table — full LLM activity trace per cycle.

Records: tool call sequence (compact), final AI reasoning, timing, emotion snapshot.

Revision ID: 004
Revises: 003
Create Date: 2026-03-17
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_cycles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("simulation_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("agent_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("agent_name", sa.String(100), nullable=False),
        sa.Column("cycle_number", sa.Integer, nullable=False),
        # Full tool call chain: [{t, in, out}] — compact, AI-readable
        sa.Column("tool_sequence", JSONB, nullable=False, server_default="[]"),
        # Final LLM response text (reasoning/conclusion)
        sa.Column("llm_reasoning", sa.Text, nullable=False, server_default=""),
        # Emotion snapshot at cycle start (VAD+ compact)
        sa.Column("emotion_snapshot", JSONB, nullable=False, server_default="{}"),
        # Timing
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        # Summary counts
        sa.Column("tool_calls_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("decisions_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("errors_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_cycle_seconds", sa.Float, nullable=False, server_default="0"),
    )
    op.create_index("ix_agent_cycles_agent_cycle", "agent_cycles", ["agent_id", "cycle_number"])


def downgrade() -> None:
    op.drop_index("ix_agent_cycles_agent_cycle", table_name="agent_cycles")
    op.drop_table("agent_cycles")

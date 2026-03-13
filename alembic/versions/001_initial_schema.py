"""Initial schema — all 16 tables + TimescaleDB hypertables + pgvector.

Revision ID: 001
Create Date: 2026-03-13
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Extensions ---
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE")

    # --- simulation_runs ---
    op.create_table(
        "simulation_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("seed", sa.Integer, nullable=False),
        sa.Column("llm_model", sa.String(100), nullable=False),
        sa.Column("llm_version", sa.String(50), server_default=""),
        sa.Column("embedding_model", sa.String(100), server_default=""),
        sa.Column("config", JSONB, server_default="{}"),
        sa.Column("initial_capital", sa.DECIMAL(20, 4), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(20), server_default="running"),
    )

    # --- roles ---
    op.create_table(
        "roles",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("simulation_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("permissions", JSONB, server_default="[]"),
        sa.Column("report_to", UUID(as_uuid=True), nullable=True),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- agents ---
    op.create_table(
        "agents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("simulation_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("role_id", UUID(as_uuid=True), nullable=True),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("philosophy", sa.Text, server_default=""),
        sa.Column("allocated_capital", sa.DECIMAL(20, 4), server_default="0"),
        sa.Column("created_by", UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- agent_personality ---
    op.create_table(
        "agent_personality",
        sa.Column("agent_id", UUID(as_uuid=True), primary_key=True),
        # Big5 (OCEAN)
        sa.Column("openness", sa.Float, server_default="0.5"),
        sa.Column("conscientiousness", sa.Float, server_default="0.5"),
        sa.Column("extraversion", sa.Float, server_default="0.5"),
        sa.Column("agreeableness", sa.Float, server_default="0.5"),
        sa.Column("neuroticism", sa.Float, server_default="0.5"),
        # HEXACO
        sa.Column("honesty_humility", sa.Float, server_default="0.5"),
        # Prospect Theory
        sa.Column("loss_aversion", sa.Float, server_default="0.5"),
        sa.Column("risk_aversion_gains", sa.Float, server_default="0.5"),
        sa.Column("risk_aversion_losses", sa.Float, server_default="0.5"),
        sa.Column("probability_weighting", sa.Float, server_default="0.5"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- agent_personality_history (TimescaleDB hypertable) ---
    op.create_table(
        "agent_personality_history",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agent_id", UUID(as_uuid=True), nullable=False),
        sa.Column("parameter", sa.String(50), nullable=False),
        sa.Column("old_value", sa.Float, nullable=False),
        sa.Column("new_value", sa.Float, nullable=False),
        sa.Column("trigger_event", sa.String(100), nullable=False),
        sa.Column("reasoning", sa.Text, server_default=""),
    )
    op.create_index("ix_agent_personality_history_agent_id", "agent_personality_history", ["agent_id"])
    op.create_index("ix_agent_personality_history_time", "agent_personality_history", ["time"])
    op.execute(
        "SELECT create_hypertable('agent_personality_history', 'time', "
        "migrate_data => true, if_not_exists => true)"
    )

    # --- agent_emotion_history (TimescaleDB hypertable) ---
    op.create_table(
        "agent_emotion_history",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agent_id", UUID(as_uuid=True), nullable=False),
        sa.Column("valence", sa.Float, nullable=False),
        sa.Column("arousal", sa.Float, nullable=False),
        sa.Column("dominance", sa.Float, nullable=False),
        sa.Column("stress", sa.Float, nullable=False),
        sa.Column("confidence", sa.Float, nullable=False),
        sa.Column("trigger", sa.String(100), server_default=""),
    )
    op.create_index("ix_agent_emotion_history_agent_id", "agent_emotion_history", ["agent_id"])
    op.create_index("ix_agent_emotion_history_time", "agent_emotion_history", ["time"])
    op.execute(
        "SELECT create_hypertable('agent_emotion_history', 'time', "
        "migrate_data => true, if_not_exists => true)"
    )

    # --- agent_decisions ---
    op.create_table(
        "agent_decisions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("simulation_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("decision_type", sa.String(50), nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("reasoning", sa.Text, server_default=""),
        sa.Column("confidence", sa.Float, server_default="0.5"),
        sa.Column("personality_snapshot", JSONB, server_default="{}"),
        sa.Column("emotion_snapshot", JSONB, server_default="{}"),
        sa.Column("context_snapshot", JSONB, server_default="{}"),
        sa.Column("outcome", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- trades ---
    op.create_table(
        "trades",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("simulation_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("agent_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("market", sa.String(20), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False, index=True),
        sa.Column("side", sa.String(10), nullable=False),
        sa.Column("order_type", sa.String(10), server_default="market"),
        sa.Column("quantity", sa.DECIMAL(20, 8), nullable=False),
        sa.Column("price", sa.DECIMAL(20, 8), nullable=False),
        sa.Column("total_value", sa.DECIMAL(20, 4), nullable=False),
        sa.Column("thesis", sa.Text, server_default=""),
        sa.Column("confidence", sa.Float, server_default="0.5"),
        sa.Column("personality_snapshot", JSONB, server_default="{}"),
        sa.Column("emotion_snapshot", JSONB, server_default="{}"),
        sa.Column("memory_refs", JSONB, server_default="[]"),
        sa.Column("executed_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("status", sa.String(20), server_default="filled"),
    )

    # --- positions ---
    op.create_table(
        "positions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("simulation_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("agent_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("market", sa.String(20), nullable=False),
        sa.Column("quantity", sa.DECIMAL(20, 8), nullable=False),
        sa.Column("avg_price", sa.DECIMAL(20, 8), nullable=False),
        sa.Column("unrealized_pnl", sa.DECIMAL(20, 4), server_default="0"),
        sa.Column("unrealized_pnl_pct", sa.Float, server_default="0"),
        sa.Column("thesis_id", UUID(as_uuid=True), nullable=True),
        sa.Column("opened_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- permission_history (TimescaleDB hypertable) ---
    op.create_table(
        "permission_history",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("agent_id", UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("changes", JSONB, nullable=False),
        sa.Column("decided_by", UUID(as_uuid=True), nullable=False),
        sa.Column("reasoning", sa.Text, server_default=""),
    )
    op.create_index("ix_permission_history_agent_id", "permission_history", ["agent_id"])
    op.create_index("ix_permission_history_time", "permission_history", ["time"])
    op.execute(
        "SELECT create_hypertable('permission_history', 'time', "
        "migrate_data => true, if_not_exists => true)"
    )

    # --- hr_events ---
    op.create_table(
        "hr_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("simulation_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("target_agent_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("decided_by", UUID(as_uuid=True), nullable=False),
        sa.Column("old_role_id", UUID(as_uuid=True), nullable=True),
        sa.Column("new_role_id", UUID(as_uuid=True), nullable=True),
        sa.Column("old_capital", sa.Float, nullable=True),
        sa.Column("new_capital", sa.Float, nullable=True),
        sa.Column("reasoning", sa.Text, server_default=""),
        sa.Column("context_snapshot", JSONB, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- agent_messages ---
    op.create_table(
        "agent_messages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("simulation_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("sender_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("receiver_id", UUID(as_uuid=True), nullable=True),
        sa.Column("priority", sa.Float, server_default="0.5"),
        sa.Column("content", JSONB, nullable=False),
        sa.Column("memory_refs", JSONB, server_default="[]"),
        sa.Column("ttl", sa.Integer, server_default="3"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # --- memories (A-MEM with pgvector embedding) ---
    op.create_table(
        "memories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("agent_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("simulation_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("memory_type", sa.String(20), nullable=False),
        sa.Column("context", sa.Text, nullable=False),
        sa.Column("keywords", JSONB, server_default="[]"),
        sa.Column("tags", JSONB, server_default="[]"),
        sa.Column("links", JSONB, server_default="[]"),
        sa.Column("q_value", sa.Float, server_default="0.5"),
        sa.Column("importance", sa.Float, server_default="0.5"),
        sa.Column("access_count", sa.Integer, server_default="0"),
        sa.Column("embedding", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_accessed", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decayed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_memories_memory_type", "memories", ["memory_type"])

    # --- episodic_details ---
    op.create_table(
        "episodic_details",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("memory_id", UUID(as_uuid=True), nullable=False, index=True),
        sa.Column("observation", sa.Text, nullable=False),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("outcome", sa.Text, nullable=False),
        sa.Column("return_pct", sa.Float, nullable=True),
        sa.Column("market_regime", sa.String(50), server_default=""),
        sa.Column("reflection", sa.Text, server_default=""),
    )

    # --- market_ohlcv (TimescaleDB hypertable) ---
    op.create_table(
        "market_ohlcv",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(20), nullable=False),
        sa.Column("market", sa.String(20), nullable=False),
        sa.Column("open", sa.DECIMAL(20, 8), nullable=False),
        sa.Column("high", sa.DECIMAL(20, 8), nullable=False),
        sa.Column("low", sa.DECIMAL(20, 8), nullable=False),
        sa.Column("close", sa.DECIMAL(20, 8), nullable=False),
        sa.Column("volume", sa.DECIMAL(20, 4), nullable=False),
        sa.Column("open_pct", sa.Float, nullable=True),
        sa.Column("high_pct", sa.Float, nullable=True),
        sa.Column("low_pct", sa.Float, nullable=True),
        sa.Column("close_pct", sa.Float, nullable=True),
        sa.Column("vol_ratio", sa.Float, nullable=True),
    )
    op.create_index("ix_market_ohlcv_symbol", "market_ohlcv", ["symbol"])
    op.create_index("ix_market_ohlcv_time", "market_ohlcv", ["time"])
    op.execute(
        "SELECT create_hypertable('market_ohlcv', 'time', "
        "migrate_data => true, if_not_exists => true)"
    )

    # --- company_snapshots (TimescaleDB hypertable) ---
    op.create_table(
        "company_snapshots",
        sa.Column("id", UUID(as_uuid=True), nullable=False),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("simulation_id", UUID(as_uuid=True), nullable=False),
        sa.Column("total_capital", sa.DECIMAL(20, 4), nullable=False),
        sa.Column("allocated_capital", sa.DECIMAL(20, 4), nullable=False),
        sa.Column("cash", sa.DECIMAL(20, 4), nullable=False),
        sa.Column("agents_count", sa.Integer, nullable=False),
        sa.Column("daily_pnl_pct", sa.Float, server_default="0"),
        sa.Column("cumulative_pnl_pct", sa.Float, server_default="0"),
        sa.Column("sharpe_30d", sa.Float, nullable=True),
        sa.Column("max_drawdown_pct", sa.Float, nullable=True),
        sa.Column("org_snapshot", JSONB, server_default="{}"),
    )
    op.create_index("ix_company_snapshots_simulation_id", "company_snapshots", ["simulation_id"])
    op.create_index("ix_company_snapshots_time", "company_snapshots", ["time"])
    op.execute(
        "SELECT create_hypertable('company_snapshots', 'time', "
        "migrate_data => true, if_not_exists => true)"
    )


def downgrade() -> None:
    op.drop_table("company_snapshots")
    op.drop_table("market_ohlcv")
    op.drop_table("episodic_details")
    op.drop_table("memories")
    op.drop_table("agent_messages")
    op.drop_table("hr_events")
    op.drop_table("permission_history")
    op.drop_table("positions")
    op.drop_table("trades")
    op.drop_table("agent_decisions")
    op.drop_table("agent_emotion_history")
    op.drop_table("agent_personality_history")
    op.drop_table("agent_personality")
    op.drop_table("agents")
    op.drop_table("roles")
    op.drop_table("simulation_runs")
    op.execute("DROP EXTENSION IF EXISTS vector")

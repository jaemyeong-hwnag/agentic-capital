"""Tests for ORM models — verify all models can be instantiated and have correct columns."""

from datetime import datetime, timezone
from uuid import uuid4

from agentic_capital.infra.models import (
    AgentCycleModel,
    AgentDecisionModel,
    AgentEmotionHistoryModel,
    AgentMessageModel,
    AgentModel,
    AgentPersonalityHistoryModel,
    AgentPersonalityModel,
    AgentToolModel,
    Base,
    CompanySnapshotModel,
    EpisodicDetailModel,
    HREventModel,
    MarketOHLCVModel,
    MemoryModel,
    PermissionHistoryModel,
    PositionModel,
    RoleModel,
    SimulationRunModel,
    TradeModel,
)


class TestAllTablesRegistered:
    def test_table_count(self) -> None:
        assert len(Base.metadata.tables) == 18

    def test_expected_tables(self) -> None:
        expected = {
            "agents", "agent_personality", "agent_personality_history",
            "agent_emotion_history", "agent_decisions", "agent_cycles",
            "trades", "positions",
            "roles", "permission_history", "hr_events", "agent_messages",
            "memories", "episodic_details", "market_ohlcv",
            "simulation_runs", "company_snapshots", "agent_tools",
        }
        assert set(Base.metadata.tables.keys()) == expected


class TestAgentModels:
    def test_agent_model(self) -> None:
        agent = AgentModel(
            id=uuid4(),
            simulation_id=uuid4(),
            name="Test Agent",
            status="active",
            allocated_capital=50000.0,
        )
        assert agent.name == "Test Agent"
        assert agent.status == "active"
        assert agent.__tablename__ == "agents"

    def test_agent_personality_model(self) -> None:
        p = AgentPersonalityModel(
            agent_id=uuid4(),
            openness=0.7,
            conscientiousness=0.8,
        )
        assert p.openness == 0.7
        assert p.__tablename__ == "agent_personality"

    def test_personality_history_model(self) -> None:
        h = AgentPersonalityHistoryModel(
            id=uuid4(),
            time=datetime.now(timezone.utc),
            agent_id=uuid4(),
            parameter="openness",
            old_value=0.5,
            new_value=0.7,
            trigger_event="big_win",
            reasoning="Successful AAPL trade increased confidence",
        )
        assert h.parameter == "openness"
        assert h.__tablename__ == "agent_personality_history"

    def test_emotion_history_model(self) -> None:
        e = AgentEmotionHistoryModel(
            id=uuid4(),
            time=datetime.now(timezone.utc),
            agent_id=uuid4(),
            valence=0.3,
            arousal=0.6,
            dominance=0.5,
            stress=0.2,
            confidence=0.7,
        )
        assert e.valence == 0.3
        assert e.__tablename__ == "agent_emotion_history"

    def test_decision_model(self) -> None:
        d = AgentDecisionModel(
            id=uuid4(),
            agent_id=uuid4(),
            simulation_id=uuid4(),
            decision_type="trade",
            action="BUY AAPL 100 shares",
            reasoning="RSI divergence detected",
            confidence=0.72,
            personality_snapshot={"openness": 0.7},
            emotion_snapshot={"valence": 0.3},
        )
        assert d.decision_type == "trade"
        assert d.__tablename__ == "agent_decisions"


class TestTradeModels:
    def test_trade_model(self) -> None:
        t = TradeModel(
            id=uuid4(),
            simulation_id=uuid4(),
            agent_id=uuid4(),
            market="us_stock",
            symbol="AAPL",
            side="buy",
            quantity=100,
            price=150.0,
            total_value=15000.0,
            thesis="RSI divergence",
            confidence=0.72,
        )
        assert t.symbol == "AAPL"
        assert t.__tablename__ == "trades"

    def test_position_model(self) -> None:
        p = PositionModel(
            id=uuid4(),
            simulation_id=uuid4(),
            agent_id=uuid4(),
            symbol="AAPL",
            market="us_stock",
            quantity=100,
            avg_price=150.0,
        )
        assert p.quantity == 100
        assert p.__tablename__ == "positions"


class TestOrganizationModels:
    def test_role_model(self) -> None:
        r = RoleModel(
            id=uuid4(),
            simulation_id=uuid4(),
            name="CIO",
            permissions=["trade_all", "allocate_capital"],
        )
        assert r.name == "CIO"
        assert r.__tablename__ == "roles"

    def test_permission_history_model(self) -> None:
        p = PermissionHistoryModel(
            id=uuid4(),
            time=datetime.now(timezone.utc),
            agent_id=uuid4(),
            action="grant",
            changes={"added": ["trade_crypto"]},
            decided_by=uuid4(),
        )
        assert p.action == "grant"
        assert p.__tablename__ == "permission_history"

    def test_hr_event_model(self) -> None:
        h = HREventModel(
            id=uuid4(),
            simulation_id=uuid4(),
            event_type="hire",
            target_agent_id=uuid4(),
            decided_by=uuid4(),
            reasoning="Need more analysts",
        )
        assert h.event_type == "hire"
        assert h.__tablename__ == "hr_events"

    def test_agent_message_model(self) -> None:
        m = AgentMessageModel(
            id=uuid4(),
            simulation_id=uuid4(),
            type="SIGNAL",
            sender_id=uuid4(),
            content={"signal": "BUY", "ticker": "AAPL"},
        )
        assert m.type == "SIGNAL"
        assert m.__tablename__ == "agent_messages"


class TestMemoryModels:
    def test_memory_model(self) -> None:
        m = MemoryModel(
            id=uuid4(),
            agent_id=uuid4(),
            simulation_id=uuid4(),
            memory_type="episodic",
            context="RSI divergence on AAPL",
            keywords=["rsi", "aapl"],
            tags=["technical"],
            q_value=0.78,
        )
        assert m.memory_type == "episodic"
        assert m.__tablename__ == "memories"

    def test_episodic_detail_model(self) -> None:
        e = EpisodicDetailModel(
            id=uuid4(),
            memory_id=uuid4(),
            observation="AAPL RSI at 34",
            action="BUY 100 shares",
            outcome="Price rose 5%",
            return_pct=0.05,
            market_regime="volatile_bullish",
        )
        assert e.return_pct == 0.05
        assert e.__tablename__ == "episodic_details"


class TestMarketModels:
    def test_ohlcv_model(self) -> None:
        o = MarketOHLCVModel(
            id=uuid4(),
            time=datetime.now(timezone.utc),
            symbol="AAPL",
            market="us_stock",
            open=150.0,
            high=155.0,
            low=149.0,
            close=153.0,
            volume=1000000,
            close_pct=0.02,
        )
        assert o.symbol == "AAPL"
        assert o.close_pct == 0.02
        assert o.__tablename__ == "market_ohlcv"


class TestSimulationModels:
    def test_simulation_run_model(self) -> None:
        s = SimulationRunModel(
            id=uuid4(),
            seed=42,
            llm_model="gemini-2.5-pro",
            initial_capital=1000000,
            config={"agents": 10},
        )
        assert s.seed == 42
        assert s.__tablename__ == "simulation_runs"

    def test_company_snapshot_model(self) -> None:
        c = CompanySnapshotModel(
            id=uuid4(),
            time=datetime.now(timezone.utc),
            simulation_id=uuid4(),
            total_capital=1050000,
            allocated_capital=900000,
            cash=150000,
            agents_count=10,
            daily_pnl_pct=0.5,
        )
        assert c.agents_count == 10
        assert c.__tablename__ == "company_snapshots"

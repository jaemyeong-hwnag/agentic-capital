"""Unit tests for backtesting pipeline."""

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from agentic_capital.core.agents.base import AgentProfile
from agentic_capital.core.agents.ceo import CEOAgent
from agentic_capital.core.agents.factory import create_random_personality
from agentic_capital.ports.llm import LLMPort
from agentic_capital.simulation.backtesting import (
    BacktestEngine,
    BacktestResult,
    HistoricalDataProvider,
    _TickMarketData,
)


def _make_llm(response='{"actions": [], "confidence": 0.5}'):
    llm = MagicMock(spec=LLMPort)
    llm.generate = AsyncMock(return_value=response)
    llm.embed = AsyncMock(return_value=[0.0] * 1024)
    return llm


class TestBacktestResult:
    def test_initial_state(self):
        result = BacktestResult()
        assert result.cycles == 0
        assert result.total_return_pct == 0.0

    def test_total_return_pct(self):
        result = BacktestResult()
        result.initial_capital = 1_000_000
        result.final_capital = 1_200_000
        assert result.total_return_pct == pytest.approx(20.0)

    def test_max_drawdown(self):
        result = BacktestResult()
        result.pnl_history = [100, 110, 105, 120, 90, 95]
        dd = result.max_drawdown_pct
        assert dd > 0  # Should detect the 120→90 drawdown (25%)
        assert dd == pytest.approx(25.0)

    def test_max_drawdown_empty(self):
        result = BacktestResult()
        assert result.max_drawdown_pct == 0.0

    def test_sharpe_ratio(self):
        result = BacktestResult()
        result.pnl_history = [100, 101, 102, 103, 104, 105]
        sharpe = result.sharpe_ratio
        assert sharpe > 0  # Consistent positive returns → positive Sharpe

    def test_sharpe_ratio_insufficient_data(self):
        result = BacktestResult()
        result.pnl_history = [100]
        assert result.sharpe_ratio == 0.0

    def test_to_dict(self):
        result = BacktestResult()
        result.initial_capital = 1_000_000
        result.final_capital = 1_100_000
        result.cycles = 10
        d = result.to_dict()
        assert d["cycles"] == 10
        assert d["total_return_pct"] == pytest.approx(10.0)


class TestHistoricalDataProvider:
    def test_load_from_dicts(self):
        provider = HistoricalDataProvider()
        data = [
            {"timestamp": "2026-01-01", "close": 70000, "volume": 1000000, "symbol": "005930"},
            {"timestamp": "2026-01-02", "close": 71000, "volume": 900000, "symbol": "005930"},
        ]
        provider.load_from_dicts(data)
        assert provider.total_ticks == 2
        assert provider.remaining_ticks == 2

    def test_get_next_tick(self):
        provider = HistoricalDataProvider()
        provider.load_from_dicts([
            {"timestamp": "2026-01-01", "close": 70000},
            {"timestamp": "2026-01-02", "close": 71000},
        ])
        tick1 = provider.get_next_tick()
        assert tick1["close"] == 70000
        tick2 = provider.get_next_tick()
        assert tick2["close"] == 71000
        tick3 = provider.get_next_tick()
        assert tick3 is None

    def test_get_window(self):
        provider = HistoricalDataProvider()
        provider.load_from_dicts([
            {"timestamp": f"2026-01-{i:02d}", "close": 70000 + i * 100}
            for i in range(1, 11)
        ])
        # Advance to tick 5
        for _ in range(5):
            provider.get_next_tick()
        window = provider.get_window(3)
        assert len(window) == 3

    def test_reset(self):
        provider = HistoricalDataProvider()
        provider.load_from_dicts([{"timestamp": "2026-01-01", "close": 70000}])
        provider.get_next_tick()
        assert provider.remaining_ticks == 0
        provider.reset()
        assert provider.remaining_ticks == 1


class TestTickMarketData:
    @pytest.mark.asyncio
    async def test_get_quote(self):
        md = _TickMarketData({"close": 72000, "volume": 5000000, "symbol": "005930"})
        quote = await md.get_quote("005930")
        assert quote.price == 72000
        assert quote.volume == 5000000

    @pytest.mark.asyncio
    async def test_get_symbols(self):
        md = _TickMarketData({"symbol": "005930"})
        symbols = await md.get_symbols()
        assert symbols == ["005930"]

    @pytest.mark.asyncio
    async def test_get_symbols_empty(self):
        md = _TickMarketData({})
        symbols = await md.get_symbols()
        assert symbols == []


class TestBacktestEngine:
    @pytest.mark.asyncio
    async def test_run_empty_data(self):
        provider = HistoricalDataProvider()
        provider.load_from_dicts([])
        engine = BacktestEngine(data_provider=provider)

        llm = _make_llm()
        agent = CEOAgent(
            profile=AgentProfile(id=uuid4(), name="CEO", philosophy="test"),
            personality=create_random_personality(42),
            llm=llm,
        )
        result = await engine.run([agent])
        assert result.cycles == 0

    @pytest.mark.asyncio
    async def test_run_with_data(self):
        provider = HistoricalDataProvider()
        provider.load_from_dicts([
            {"timestamp": "2026-01-01", "close": 70000, "volume": 1000000, "symbol": "005930"},
            {"timestamp": "2026-01-02", "close": 71000, "volume": 900000, "symbol": "005930"},
            {"timestamp": "2026-01-03", "close": 72000, "volume": 800000, "symbol": "005930"},
        ])
        engine = BacktestEngine(initial_capital=10_000_000, data_provider=provider)

        llm = _make_llm('{"actions": [], "confidence": 0.5}')
        agent = CEOAgent(
            profile=AgentProfile(id=uuid4(), name="CEO", philosophy="test"),
            personality=create_random_personality(42),
            llm=llm,
        )
        result = await engine.run([agent], symbols=["005930"])
        assert result.cycles == 3
        assert result.initial_capital == 10_000_000
        assert len(result.pnl_history) == 3

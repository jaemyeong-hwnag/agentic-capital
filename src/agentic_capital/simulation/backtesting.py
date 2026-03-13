"""Backtesting pipeline — replay historical data through agent workflows.

Uses DuckDB for fast analytical queries on historical market data.
Agents run the same LangGraph workflow as live trading — only the
data source changes (historical vs live).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


class BacktestResult:
    """Results from a backtesting run."""

    def __init__(self) -> None:
        self.cycles: int = 0
        self.total_trades: int = 0
        self.pnl_history: list[float] = []
        self.decisions: list[dict] = []
        self.final_capital: float = 0.0
        self.initial_capital: float = 0.0
        self.start_date: datetime | None = None
        self.end_date: datetime | None = None

    @property
    def total_return_pct(self) -> float:
        if self.initial_capital == 0:
            return 0.0
        return ((self.final_capital - self.initial_capital) / self.initial_capital) * 100

    @property
    def max_drawdown_pct(self) -> float:
        if not self.pnl_history:
            return 0.0
        peak = self.pnl_history[0]
        max_dd = 0.0
        for value in self.pnl_history:
            if value > peak:
                peak = value
            dd = (peak - value) / peak * 100 if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
        return max_dd

    @property
    def sharpe_ratio(self) -> float:
        """Annualized Sharpe ratio (assuming daily returns)."""
        if len(self.pnl_history) < 2:
            return 0.0
        import numpy as np
        returns = np.diff(self.pnl_history) / np.array(self.pnl_history[:-1])
        returns = returns[np.isfinite(returns)]
        if len(returns) == 0 or np.std(returns) == 0:
            return 0.0
        return float(np.mean(returns) / np.std(returns) * np.sqrt(252))

    def to_dict(self) -> dict:
        return {
            "cycles": self.cycles,
            "total_trades": self.total_trades,
            "initial_capital": self.initial_capital,
            "final_capital": self.final_capital,
            "total_return_pct": self.total_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "start_date": str(self.start_date) if self.start_date else None,
            "end_date": str(self.end_date) if self.end_date else None,
        }


class HistoricalDataProvider:
    """Provides historical market data from DuckDB or CSV/Parquet files.

    Simulates MarketDataPort interface using stored data.
    """

    def __init__(self, data_path: str | Path | None = None) -> None:
        self._data_path = Path(data_path) if data_path else None
        self._db = None
        self._current_idx = 0
        self._data: list[dict] = []

    def load_from_dicts(self, data: list[dict]) -> None:
        """Load data from a list of dicts (for testing)."""
        self._data = sorted(data, key=lambda d: d.get("timestamp", ""))
        self._current_idx = 0

    def load_from_duckdb(self, query: str) -> None:
        """Load data from DuckDB query."""
        try:
            import duckdb
            conn = duckdb.connect()
            if self._data_path:
                result = conn.execute(query.replace("{path}", str(self._data_path))).fetchall()
                columns = [desc[0] for desc in conn.description]
                self._data = [dict(zip(columns, row)) for row in result]
            conn.close()
            self._current_idx = 0
            logger.info("duckdb_data_loaded", rows=len(self._data))
        except Exception as e:
            logger.exception("duckdb_load_failed", error=str(e))

    def load_from_file(self, file_path: str | Path) -> None:
        """Load data from CSV or Parquet file via DuckDB."""
        path = Path(file_path)
        try:
            import duckdb
            conn = duckdb.connect()
            if path.suffix == ".parquet":
                result = conn.execute(f"SELECT * FROM read_parquet('{path}')").fetchall()
            elif path.suffix == ".csv":
                result = conn.execute(f"SELECT * FROM read_csv_auto('{path}')").fetchall()
            else:
                logger.warning("unsupported_file_format", suffix=path.suffix)
                return
            columns = [desc[0] for desc in conn.description]
            self._data = [dict(zip(columns, row)) for row in result]
            conn.close()
            self._current_idx = 0
            logger.info("file_data_loaded", path=str(path), rows=len(self._data))
        except Exception as e:
            logger.exception("file_load_failed", error=str(e))

    def get_next_tick(self) -> dict | None:
        """Get next data point in time series."""
        if self._current_idx >= len(self._data):
            return None
        data = self._data[self._current_idx]
        self._current_idx += 1
        return data

    def get_window(self, size: int = 30) -> list[dict]:
        """Get a window of data points up to current position."""
        start = max(0, self._current_idx - size)
        return self._data[start:self._current_idx]

    def reset(self) -> None:
        """Reset to beginning of data."""
        self._current_idx = 0

    @property
    def total_ticks(self) -> int:
        return len(self._data)

    @property
    def remaining_ticks(self) -> int:
        return max(0, len(self._data) - self._current_idx)


class BacktestEngine:
    """Run agent workflows against historical data.

    Uses the same LangGraph workflow as live trading.
    Only the data source differs — historical instead of live.
    """

    def __init__(
        self,
        *,
        initial_capital: float = 10_000_000,
        data_provider: HistoricalDataProvider | None = None,
    ) -> None:
        self._initial_capital = initial_capital
        self._data_provider = data_provider or HistoricalDataProvider()
        self._result = BacktestResult()

    async def run(
        self,
        agents: list[Any],
        symbols: list[str] | None = None,
    ) -> BacktestResult:
        """Run backtest for all agents against historical data.

        Each tick of historical data triggers one cycle for all agents.
        """
        from agentic_capital.graph.workflow import run_agent_cycle

        self._result = BacktestResult()
        self._result.initial_capital = self._initial_capital
        capital = self._initial_capital

        self._data_provider.reset()
        cycle = 0

        while True:
            tick = self._data_provider.get_next_tick()
            if tick is None:
                break

            cycle += 1
            if cycle == 1:
                self._result.start_date = tick.get("timestamp")

            # Create a mock market data source for this tick
            mock_md = _TickMarketData(tick)

            for agent in agents:
                try:
                    result = await run_agent_cycle(
                        agent,
                        cycle_number=cycle,
                        market_data=mock_md,
                        symbols=symbols or [tick.get("symbol", "")],
                    )

                    decisions = result.get("decisions", [])
                    self._result.decisions.extend(decisions)
                    self._result.total_trades += sum(
                        1 for d in decisions
                        if isinstance(d, dict) and d.get("action") in ("BUY", "SELL")
                    )

                except Exception:
                    logger.warning("backtest_agent_failed", agent=agent.name, cycle=cycle)

            self._result.pnl_history.append(capital)
            self._result.end_date = tick.get("timestamp")

        self._result.cycles = cycle
        self._result.final_capital = capital

        logger.info(
            "backtest_complete",
            cycles=cycle,
            trades=self._result.total_trades,
            return_pct=f"{self._result.total_return_pct:.2f}%",
        )

        return self._result


class _TickMarketData:
    """Minimal market data adapter from a single historical tick."""

    def __init__(self, tick: dict) -> None:
        self._tick = tick

    async def get_quote(self, symbol: str) -> Any:
        from types import SimpleNamespace
        return SimpleNamespace(
            price=self._tick.get("close", self._tick.get("price", 0)),
            volume=self._tick.get("volume", 0),
            bid=None,
            ask=None,
        )

    async def get_symbols(self) -> list[str]:
        symbol = self._tick.get("symbol", "")
        return [symbol] if symbol else []

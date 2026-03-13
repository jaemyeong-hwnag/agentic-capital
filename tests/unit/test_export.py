"""Unit tests for data export."""

import tempfile
from pathlib import Path

import pytest

from agentic_capital.simulation.export import DataExporter


class TestDataExporter:
    def test_export_to_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = DataExporter(output_dir=tmpdir)
            data = [
                {"symbol": "005930", "price": 70000, "action": "BUY"},
                {"symbol": "000660", "price": 90000, "action": "SELL"},
            ]
            path = exporter.export_to_csv(data, "test.csv")
            assert path.exists()
            content = path.read_text()
            assert "005930" in content
            assert "000660" in content
            assert "symbol,price,action" in content

    def test_export_to_csv_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = DataExporter(output_dir=tmpdir)
            path = exporter.export_to_csv([], "empty.csv")
            assert not path.exists()  # No file created for empty data

    def test_export_to_parquet(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = DataExporter(output_dir=tmpdir)
            data = [
                {"symbol": "005930", "price": 70000},
                {"symbol": "000660", "price": 90000},
            ]
            path = exporter.export_to_parquet(data, "test.parquet")
            assert path.exists()
            assert path.stat().st_size > 0

    def test_export_to_parquet_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = DataExporter(output_dir=tmpdir)
            path = exporter.export_to_parquet([], "empty.parquet")
            # Path returned but file not created for empty data
            assert not path.exists()

    def test_export_backtest_result(self):
        from agentic_capital.simulation.backtesting import BacktestResult

        with tempfile.TemporaryDirectory() as tmpdir:
            exporter = DataExporter(output_dir=tmpdir)
            result = BacktestResult()
            result.initial_capital = 1_000_000
            result.final_capital = 1_100_000
            result.cycles = 10
            result.pnl_history = [1_000_000, 1_050_000, 1_100_000]
            result.decisions = [{"action": "BUY", "symbol": "005930"}]

            paths = exporter.export_backtest_result(result, prefix="test")
            assert "summary" in paths
            assert paths["summary"].exists()
            assert "pnl" in paths
            assert paths["pnl"].exists()
            assert "decisions" in paths
            assert paths["decisions"].exists()

    def test_creates_output_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            nested = Path(tmpdir) / "nested" / "dir"
            exporter = DataExporter(output_dir=nested)
            assert nested.exists()

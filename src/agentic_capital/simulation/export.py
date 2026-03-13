"""Data export — Parquet/CSV export for analysis and paper datasets.

Exports simulation data in formats suitable for:
- Academic paper datasets (reproducible research)
- External analysis tools (pandas, R, etc.)
- Archival and backup
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger()


class DataExporter:
    """Export simulation data to Parquet/CSV formats."""

    def __init__(self, output_dir: str | Path = "exports") -> None:
        self._output_dir = Path(output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def export_to_parquet(self, data: list[dict], filename: str) -> Path:
        """Export data to Parquet format via PyArrow."""
        import pyarrow as pa
        import pyarrow.parquet as pq

        if not data:
            logger.warning("export_empty_data", filename=filename)
            return self._output_dir / filename

        table = pa.Table.from_pylist(data)
        output_path = self._output_dir / filename
        pq.write_table(table, output_path)

        logger.info("exported_parquet", path=str(output_path), rows=len(data))
        return output_path

    def export_to_csv(self, data: list[dict], filename: str) -> Path:
        """Export data to CSV format."""
        import csv

        if not data:
            logger.warning("export_empty_data", filename=filename)
            return self._output_dir / filename

        output_path = self._output_dir / filename
        keys = list(data[0].keys())

        with open(output_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)

        logger.info("exported_csv", path=str(output_path), rows=len(data))
        return output_path

    def export_backtest_result(self, result: Any, prefix: str = "backtest") -> dict[str, Path]:
        """Export a BacktestResult to multiple files."""
        paths = {}

        # Summary
        summary_path = self.export_to_csv(
            [result.to_dict()],
            f"{prefix}_summary.csv",
        )
        paths["summary"] = summary_path

        # PnL history
        if result.pnl_history:
            pnl_data = [{"cycle": i, "capital": v} for i, v in enumerate(result.pnl_history)]
            paths["pnl"] = self.export_to_csv(pnl_data, f"{prefix}_pnl.csv")

        # Decisions
        if result.decisions:
            # Flatten nested dicts for CSV compatibility
            flat_decisions = []
            for d in result.decisions:
                if isinstance(d, dict):
                    flat_decisions.append({k: str(v) for k, v in d.items()})
            if flat_decisions:
                paths["decisions"] = self.export_to_csv(flat_decisions, f"{prefix}_decisions.csv")

        logger.info("backtest_exported", files=list(paths.keys()))
        return paths

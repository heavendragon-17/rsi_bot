"""
Backtest Reporter (Thin Formatter)
====================================
Formats pre-computed results dict from BacktestEngine.compute_results() into:
- HTML report with charts
- CSV export of round-trip trades

All metric computation lives in BacktestEngine. This class is purely a formatter.
HTML generation is delegated to reporting_html module.
"""

import os

import pandas as pd
import structlog

from app.backtest.reporting.html import generate_html_report

logger = structlog.get_logger()


class BacktestReporter:
    """Format and export backtest results. Receives a pre-computed results dict."""

    def __init__(
        self,
        results: dict,
        symbol: str,
        timeframe: str,
        strategy_name: str,
        leverage: int = 1,
        strategy_params: dict = None,
    ):
        self.results = results
        self.symbol = symbol
        self.timeframe = timeframe
        self.strategy_name = strategy_name
        self.leverage = leverage
        self.strategy_params = strategy_params or {}

    def generate_report(self, output_dir: str = ".") -> str | None:
        """Generate HTML and CSV reports from pre-computed results."""
        round_trips = self.results.get("round_trips", [])
        if not round_trips and self.results.get("metrics", {}).get("total_trades", 0) == 0:
            logger.info("no_trades_executed")
            return None

        os.makedirs(output_dir, exist_ok=True)
        report_path = generate_html_report(
            results=self.results,
            symbol=self.symbol,
            timeframe=self.timeframe,
            strategy_name=self.strategy_name,
            leverage=self.leverage,
            strategy_params=self.strategy_params,
            return_only=False,
            output_dir=output_dir,
        )
        self._export_csv(output_dir=output_dir)
        return report_path

    def _generate_html_report(self, return_only: bool = False, output_dir: str = ".") -> str | None:
        """Generate HTML report. Delegates to reporting_html module."""
        return generate_html_report(
            results=self.results,
            symbol=self.symbol,
            timeframe=self.timeframe,
            strategy_name=self.strategy_name,
            leverage=self.leverage,
            strategy_params=self.strategy_params,
            return_only=return_only,
            output_dir=output_dir,
        )

    def _export_csv(self, output_dir: str = ".") -> None:
        """Export round-trip trades to CSV."""
        rt_list = self.results.get("round_trips", [])
        if not rt_list:
            return

        safe_symbol = self.symbol.replace("/", "")
        csv_dir = os.path.join(output_dir, "csv")
        os.makedirs(csv_dir, exist_ok=True)

        round_trips_df = pd.DataFrame(rt_list)
        trades_path = os.path.join(csv_dir, f"backtest_trades_{safe_symbol}_{self.timeframe}.csv")
        round_trips_df.to_csv(trades_path, index=False)
        logger.info("csv_exported", path=trades_path)

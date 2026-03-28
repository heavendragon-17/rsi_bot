"""Backtest engine sub-package — core simulation logic."""

from app.backtest.engine.backtest_engine import BacktestEngine
from app.backtest.engine.curves import build_drawdown_curve_dated, build_equity_curve_dated
from app.backtest.engine.event_source import BacktestEventSource
from app.backtest.engine.metrics import (
    build_round_trips,
    calculate_drawdown,
    calculate_metrics,
    calculate_monthly_returns,
    calculate_risk_metrics,
)
from app.backtest.engine.portfolio_engine import PortfolioEngine
from app.backtest.engine.batch_event_source import BatchPortfolioEventSource
from app.backtest.engine.portfolio_event_source import PortfolioEventSource

__all__ = [
    "BacktestEngine",
    "BacktestEventSource",
    "BatchPortfolioEventSource",
    "PortfolioEngine",
    "PortfolioEventSource",
    "build_drawdown_curve_dated",
    "build_equity_curve_dated",
    "build_round_trips",
    "calculate_drawdown",
    "calculate_metrics",
    "calculate_monthly_returns",
    "calculate_risk_metrics",
]

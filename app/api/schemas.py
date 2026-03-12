"""
Pydantic schemas — source of truth for all API request/response shapes.

TypeScript types are auto-generated from these via `npm run generate-types`.
Do NOT add hand-written TypeScript interfaces for these models.
"""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class BacktestRequest(BaseModel):
    mode: Literal["single", "batch", "portfolio"]
    symbols: list[str]               # single → use symbols[0]
    timeframe: str
    strategy: str
    start_date: str                  # yyyy-MM-dd
    end_date: str
    initial_capital: str = "10000"
    capital_mode: Literal["split", "full"] = "split"   # batch only
    leverage: int = 10
    risk_per_trade_pct: str = "0.02"
    fee_tier: str = "0.001"
    slippage_model: str = "none"
    slippage_pct: str = "0.0"
    params: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Backtest responses
# ---------------------------------------------------------------------------


class BacktestStartResponse(BaseModel):
    run_id: int | None = None          # For single mode — existing Run row
    batch_run_id: int | None = None    # For batch mode — new BatchRun row
    portfolio_run_id: int | None = None  # For portfolio mode — new PortfolioRun row
    mode: str
    status: str          # "running"


class BatchSymbolResult(BaseModel):
    symbol: str
    status: Literal["completed", "failed"]
    error: str | None = None
    net_profit: str | None = None
    net_profit_pct: float | None = None
    win_rate: float | None = None
    profit_factor: float | None = None
    max_drawdown_pct: float | None = None
    sharpe_ratio: float | None = None
    total_trades: int | None = None
    trades: list[dict[str, Any]] | None = None


class BatchRunDetail(BaseModel):
    id: int
    mode: Literal["batch"] = "batch"
    strategy_name: str
    timeframe: str
    status: str
    created_at: str
    config: dict[str, Any]
    capital_mode: str            # "split" | "full"
    symbol_count: int
    failed_symbols: list[str]
    aggregate: dict[str, Any]    # total_pnl, portfolio_return, avg_sharpe, total_trades, etc.
    symbols: list[BatchSymbolResult]


class PortfolioRunDetail(BaseModel):
    id: int
    mode: Literal["portfolio"] = "portfolio"
    strategy_name: str
    timeframe: str
    status: str
    created_at: str
    config: dict[str, Any]
    symbols: list[str]
    results: dict[str, Any]      # same shape as single RunResult (shared portfolio metrics)
    trades: list[dict[str, Any]] # all trades with symbol field


class BatchTimeseriesResponse(BaseModel):
    batch_run_id: int
    portfolio_equity_curve: list[dict[str, Any]]   # aggregate equity over time
    per_symbol_equity: dict[str, list[dict[str, Any]]]        # symbol → equity curve
    monthly_returns: dict[str, Any]


class PortfolioTimeseriesResponse(BaseModel):
    portfolio_run_id: int
    equity_curve: list[dict[str, Any]]
    drawdown_curve: list[dict[str, Any]]
    monthly_returns: dict[str, Any]


class RunSummary(BaseModel):
    """Lightweight row for history list — no heavy timeseries data."""
    id: int
    strategy_name: str
    symbol: str
    timeframe: str
    status: str
    created_at: str
    start_date: str
    end_date: str
    initial_capital: str            # TEXT — frontend must parseFloat()
    leverage: int
    net_profit: str | None          # TEXT — frontend must parseFloat()
    net_profit_pct: float | None
    win_rate: float | None
    profit_factor: float | None
    max_drawdown_pct: float | None
    sharpe_ratio: float | None
    total_trades: int | None
    tags: list[str]


class RunDetail(BaseModel):
    id: int
    strategy_name: str
    symbol: str
    timeframe: str
    status: str
    created_at: str
    config: dict[str, Any]
    results: dict[str, Any] | None      # All RunResult fields, flat
    trades: list[dict[str, Any]] | None


# ---------------------------------------------------------------------------
# Timeseries (lazy-loaded separately to keep RunDetail lightweight)
# ---------------------------------------------------------------------------


class TimeseriesResponse(BaseModel):
    run_id: int
    equity_curve: list[dict[str, Any]]      # [{date, balance}]
    drawdown_curve: list[dict[str, Any]]    # [{date, drawdown}]
    monthly_returns: dict[str, Any]


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


class HistoryResponse(BaseModel):
    runs: list[RunSummary]
    total: int
    page: int
    pages: int


# ---------------------------------------------------------------------------
# Data availability
# ---------------------------------------------------------------------------


class DataStatusResponse(BaseModel):
    symbol: str
    timeframe: str
    available: bool
    file_path: str | None
    candle_count: int | None
    date_range: dict[str, str] | None  # {start, end}


class DownloadStartResponse(BaseModel):
    job_id: str
    status: str


# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------


class StrategyInfo(BaseModel):
    id: int
    name: str
    description: str | None
    default_config: dict[str, Any]

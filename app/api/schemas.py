"""
Pydantic schemas — source of truth for all API request/response shapes.

TypeScript types are auto-generated from these via `npm run generate-types`.
Do NOT add hand-written TypeScript interfaces for these models.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_validator


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class BacktestRequest(BaseModel):
    """Unified backtest request. Provide exactly one of `symbol` (single) or `symbols` (portfolio)."""
    symbol: str | None = None           # Single-symbol mode
    symbols: list[str] | None = None    # Portfolio mode
    timeframe: str
    strategy: str
    start_date: str
    end_date: str
    initial_capital: str = "10000.00"   # TEXT / Decimal string
    leverage: int = 10
    risk_per_trade_pct: str = "0.02"
    fee_tier: str = "0.001"
    slippage_model: str = "none"
    slippage_pct: str = "0.0"
    params: dict[str, Any] = {}

    @model_validator(mode="after")
    def _check_symbol_xor_symbols(self) -> "BacktestRequest":
        has_single = bool(self.symbol)
        has_multi = bool(self.symbols)
        if has_single == has_multi:
            raise ValueError("Provide exactly one of 'symbol' (single) or 'symbols' (portfolio)")
        return self


# ---------------------------------------------------------------------------
# Backtest responses
# ---------------------------------------------------------------------------


class BacktestStartResponse(BaseModel):
    run_id: int
    status: str


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

"""
Pydantic schemas — source of truth for all API request/response shapes.

TypeScript types are auto-generated from these via `npm run generate-types`.
Do NOT add hand-written TypeScript interfaces for these models.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, model_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BacktestMode(StrEnum):
    SINGLE = "single"
    PORTFOLIO = "portfolio"
    BATCH = "batch"
    TICK_REPLAY = "tick_replay"


class SignalQuality(StrEnum):
    UNREVIEWED = "UNREVIEWED"
    GOOD = "GOOD"
    BAD = "BAD"
    UNCERTAIN = "UNCERTAIN"


class SignalHumanOutcome(StrEnum):
    UNSET = "UNSET"
    WIN = "WIN"
    LOSS = "LOSS"
    SKIP = "SKIP"


# ---------------------------------------------------------------------------
# Request
# ---------------------------------------------------------------------------


class BacktestRequest(BaseModel):
    """Unified backtest request with explicit mode selection."""

    mode: BacktestMode | None = None  # Explicit mode (auto-detected if omitted)
    symbol: str | None = None  # single, tick_replay
    symbols: list[str] | None = None  # portfolio, batch
    timeframe: str
    strategy: str
    start_date: str
    end_date: str
    initial_capital: str = "10000.00"  # TEXT / Decimal string
    leverage: int = 10
    risk_per_trade_pct: str = "0.02"
    taker_fee_pct: str = "0.10"  # Percentage, e.g. "0.10" = 0.10% = 0.001 decimal
    maker_fee_pct: str = "0.10"  # Percentage, e.g. "0.06" = 0.06%
    slippage_model: str = "none"
    slippage_pct: str = "0.0"
    params: dict[str, Any] = {}
    benchmark: str | None = None  # buy-and-hold symbol, e.g. "BTC/USDT"
    max_workers: int | None = None  # batch only
    tick_data_path: str | None = None  # tick_replay only

    # --- Risk / portfolio params (defaults match config.yaml) ---
    tp1_close_pct: float = 1.0  # Close 100% at TP1
    tp2_close_pct: float = 0.0  # Close 0% at TP2
    max_position_size_pct: float = 10.0  # Max margin % per trade
    min_sl_distance_pct: float = 0.003  # Min SL distance
    use_risk_based_sizing: bool = True  # Size based on SL distance
    use_initial_capital_for_risk: bool = True  # Risk off initial capital

    @model_validator(mode="after")
    def _validate_mode_fields(self) -> BacktestRequest:
        if self.mode in (BacktestMode.SINGLE, BacktestMode.TICK_REPLAY):
            if not self.symbol:
                raise ValueError(f"mode={self.mode.value} requires 'symbol'")
        elif self.mode in (BacktestMode.PORTFOLIO, BacktestMode.BATCH):
            if not self.symbols:
                raise ValueError(f"mode={self.mode.value} requires 'symbols'")
        elif self.mode is None:
            # Backward compat: infer mode from symbol/symbols
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
    initial_capital: str  # TEXT — frontend must parseFloat()
    leverage: int
    net_profit: str | None  # TEXT — frontend must parseFloat()
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
    results: dict[str, Any] | None  # All RunResult fields, flat
    trades: list[dict[str, Any]] | None


# ---------------------------------------------------------------------------
# Timeseries (lazy-loaded separately to keep RunDetail lightweight)
# ---------------------------------------------------------------------------


class TimeseriesResponse(BaseModel):
    run_id: int
    equity_curve: list[dict[str, Any]]  # [{date, balance}]
    drawdown_curve: list[dict[str, Any]]  # [{date, drawdown}]
    monthly_returns: dict[str, Any]
    dispersion_range: list[dict[str, Any]]  # [{date, min, max}] — batch/portfolio only
    benchmark_curve: list[dict[str, Any]]  # [{date, balance}] — optional buy-and-hold


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
    param_schema: dict[str, Any] = {}


# ---------------------------------------------------------------------------
# Presets
# ---------------------------------------------------------------------------


class PresetCreate(BaseModel):
    name: str
    strategy: str
    config: dict[str, Any]


class PresetUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None


class PresetResponse(BaseModel):
    id: int
    name: str
    strategy: str
    config: dict[str, Any]
    created_at: str
    updated_at: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# BTC signal replay review
# ---------------------------------------------------------------------------


class SignalReplayRunRequest(BaseModel):
    """Start a BTC M5/M15 replay using the canonical local CSV files."""

    start: str | None = None
    end: str | None = None


class SignalReplayStartResponse(BaseModel):
    run_id: int
    status: str


class SignalReplaySourceAvailability(BaseModel):
    timeframe: str
    available: bool
    row_count: int
    available_start: str | None
    available_end: str | None
    source_modified_at: str | None
    error: str | None


class SignalReplayAvailabilityResponse(BaseModel):
    ready: bool
    common_start_at: str | None
    common_end_at: str | None
    sources: list[SignalReplaySourceAvailability]


class SignalReplayRunSummary(BaseModel):
    id: int
    status: str
    strategy_name: str
    definition_version: str
    git_hash: str | None
    symbol: str
    requested_start_at: str | None
    requested_end_at: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    signal_count: int
    m5_count: int
    m15_count: int
    error_message: str | None


class SignalForwardMetricResponse(BaseModel):
    horizon_minutes: int
    price_at_observation: str | None
    return_pct: float | None
    mfe_pct: float | None
    mae_pct: float | None
    observed_at: str | None
    complete: bool
    warning: str | None


class SignalReviewResponse(BaseModel):
    quality: SignalQuality
    human_outcome: SignalHumanOutcome
    note: str | None
    reviewed_at: str | None
    updated_at: str | None
    future_unlocked_at: str | None


class SignalReviewUpdate(BaseModel):
    quality: SignalQuality | None = None
    human_outcome: SignalHumanOutcome | None = None
    note: str | None = None


class SignalReplaySignalSummary(BaseModel):
    id: int
    replay_run_id: int
    event_id: str
    sequence: int
    timeframe: str
    trigger_close_at: str
    trigger_close_price: str
    decision_reason: str
    quality: SignalQuality
    human_outcome: SignalHumanOutcome
    note_present: bool


class SignalReplaySignalDetail(BaseModel):
    id: int
    replay_run_id: int
    event_id: str
    sequence: int
    timeframe: str
    definition_version: str
    trigger_open_at: str
    trigger_close_at: str
    trigger_close_price: str
    trigger_price_ema21: str
    rsi21: float
    rsi_ema9: float
    rsi_wma45: float
    rsi_spread: float
    previous_rsi_ema9: float | None
    previous_rsi_wma45: float | None
    h4_close_price: str
    h4_price_ema21: str
    h4_close_at: str
    decision_reason: str
    telegram_card: str
    snapshot: dict[str, Any]
    review: SignalReviewResponse
    forward_metrics: list[SignalForwardMetricResponse]


class SignalReplayListResponse(BaseModel):
    signals: list[SignalReplaySignalSummary]
    total: int
    page: int
    pages: int


class SignalReplayRunDetail(BaseModel):
    run: SignalReplayRunSummary
    source_metadata: dict[str, Any]
    counters: dict[str, Any]


class SignalChartResponse(BaseModel):
    signal_id: int
    timeframe: str
    candles: list[dict[str, Any]]
    available_start: str | None
    available_end: str | None
    requested_start: str | None
    requested_end: str | None
    has_before: bool
    has_after: bool
    future_allowed: bool
    warning: str | None

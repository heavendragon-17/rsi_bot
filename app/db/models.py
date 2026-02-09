from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from decimal import Decimal

# Shared Types
class Strategy(BaseModel):
    id: Optional[int] = None
    name: str
    description: Optional[str] = None
    default_config: Dict[str, Any]
    created_at: Optional[datetime] = None

class Theme(BaseModel):
    id: Optional[int] = None
    name: str
    display_name: str
    is_dark: bool = True
    css_variables: Dict[str, str]
    created_at: Optional[datetime] = None

class Run(BaseModel):
    id: Optional[int] = None
    strategy_id: int
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    status: str = "pending"
    git_hash: Optional[str] = None
    version: Optional[str] = None
    is_grid_search: bool = False
    grid_search_parent_id: Optional[int] = None
    grid_search_total: Optional[int] = None
    grid_search_completed: Optional[int] = None

class RunConfig(BaseModel):
    id: Optional[int] = None
    run_id: int
    symbol: str
    symbols_list: Optional[List[str]] = None
    is_batch_mode: bool = False
    timeframe: str
    start_date: datetime
    end_date: datetime
    lookback_value: Optional[int] = None
    lookback_unit: Optional[str] = None
    initial_capital: Decimal = Decimal("10000.00")
    leverage: int = 10
    risk_per_trade_pct: Decimal = Decimal("0.02")
    fee_tier: Decimal = Decimal("0.001")
    slippage_model: str = "none"
    slippage_pct: Decimal = Decimal("0.0")
    params: Dict[str, Any]

class RunResult(BaseModel):
    id: Optional[int] = None
    run_id: int
    net_profit: Optional[Decimal] = None
    net_profit_pct: Optional[float] = None
    gross_profit: Optional[Decimal] = None
    gross_loss: Optional[Decimal] = None
    win_rate: Optional[float] = None
    profit_factor: Optional[float] = None
    expectancy: Optional[Decimal] = None
    max_drawdown_pct: Optional[float] = None
    max_drawdown_value: Optional[Decimal] = None
    max_drawdown_duration_days: Optional[float] = None
    volatility: Optional[float] = None
    sharpe_ratio: Optional[float] = None
    sortino_ratio: Optional[float] = None
    calmar_ratio: Optional[float] = None
    total_trades: Optional[int] = None
    winning_trades: Optional[int] = None
    losing_trades: Optional[int] = None
    avg_win: Optional[Decimal] = None
    avg_loss: Optional[Decimal] = None
    largest_win: Optional[Decimal] = None
    largest_loss: Optional[Decimal] = None
    max_consecutive_wins: Optional[int] = None
    max_consecutive_losses: Optional[int] = None
    avg_hold_time_hours: Optional[float] = None
    exit_reasons: Optional[Dict[str, int]] = None

class Trade(BaseModel):
    id: Optional[int] = None
    run_id: int
    symbol: str
    side: str
    entry_time: datetime
    exit_time: Optional[datetime] = None
    hold_time_hours: Optional[float] = None
    entry_price: Decimal
    exit_price: Optional[Decimal] = None
    stop_loss_price: Optional[Decimal] = None
    tp1_price: Optional[Decimal] = None
    tp2_price: Optional[Decimal] = None
    tp3_price: Optional[Decimal] = None
    quantity: Decimal
    size_usd: Decimal
    pnl: Optional[Decimal] = None
    pnl_pct: Optional[float] = None
    exit_reason: Optional[str] = None
    note: Optional[str] = None

class RunTimeseries(BaseModel):
    run_id: int
    equity_curve: List[Dict[str, Any]]  # [{"date": "...", "balance": ...}]
    drawdown_curve: List[Dict[str, Any]]
    monthly_returns: Dict[str, float]

"""
ORM models for the backtest database.

The database contains two deliberately separate result domains:

* order-oriented backtests (`runs`, `trades`, and related tables); and
* signal-review replays (`signal_replay_runs`, `replay_signals`,
  `signal_reviews`, and `signal_forward_metrics`).

The second domain must not be represented as trades because a raw BTC alert
does not contain an execution, fill, stop, target, or PnL model.
"""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.types import JSON

from app.repository.backtest.database import Base


class Strategy(Base):
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False, unique=True)
    description = Column(Text)
    default_config = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    runs = relationship("Run", back_populates="strategy")


class Batch(Base):
    __tablename__ = "batches"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(Text, default="running")  # running, completed, partial, failed
    total_symbols = Column(Integer)
    completed_symbols = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    runs = relationship("Run", back_populates="batch")


class Run(Base):
    __tablename__ = "runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    status = Column(Text, default="pending")  # pending|running|completed|failed|cancelled
    git_hash = Column(Text)
    version = Column(Text)
    is_grid_search = Column(Boolean, default=False)
    grid_search_parent_id = Column(Integer, ForeignKey("runs.id"))
    grid_search_total = Column(Integer)
    grid_search_completed = Column(Integer)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=True)

    strategy = relationship("Strategy", back_populates="runs")
    batch = relationship("Batch", back_populates="runs")
    config = relationship("RunConfig", back_populates="run", uselist=False, cascade="all, delete-orphan")
    result = relationship("RunResult", back_populates="run", uselist=False, cascade="all, delete-orphan")
    timeseries = relationship("RunTimeseries", back_populates="run", uselist=False, cascade="all, delete-orphan")
    trades = relationship("Trade", back_populates="run", cascade="all, delete-orphan")
    tags = relationship("Tag", back_populates="run", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_runs_strategy", "strategy_id"),
        Index("idx_runs_created", "created_at"),
        Index("idx_runs_status", "status"),
    )


class RunConfig(Base):
    __tablename__ = "run_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False, unique=True)
    symbol = Column(Text, nullable=False)
    symbols_list = Column(JSON)
    is_batch_mode = Column(Boolean, default=False)
    timeframe = Column(Text, nullable=False)
    start_date = Column(Date, nullable=False)
    end_date = Column(Date, nullable=False)
    lookback_value = Column(Integer)
    lookback_unit = Column(Text)
    initial_capital = Column(Text, default="10000.00")
    leverage = Column(Integer, default=10)
    risk_per_trade_pct = Column(Text, default="0.02")
    fee_tier = Column(Text, default="0.001")
    slippage_model = Column(Text, default="none")
    slippage_pct = Column(Text, default="0.0")
    params = Column(JSON, nullable=False)

    run = relationship("Run", back_populates="config")


class RunResult(Base):
    __tablename__ = "run_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False, unique=True)
    final_balance = Column(Text)
    net_profit = Column(Text)
    net_profit_pct = Column(Float)
    gross_profit = Column(Text)
    gross_loss = Column(Text)
    win_rate = Column(Float)
    profit_factor = Column(Float)
    expectancy = Column(Text)
    max_drawdown_pct = Column(Float)
    max_drawdown_value = Column(Text)
    max_drawdown_duration_days = Column(Float)
    volatility = Column(Float)
    sharpe_ratio = Column(Float)
    sortino_ratio = Column(Float)
    calmar_ratio = Column(Float)
    total_trades = Column(Integer)
    winning_trades = Column(Integer)
    losing_trades = Column(Integer)
    avg_win = Column(Text)
    avg_loss = Column(Text)
    largest_win = Column(Text)
    largest_loss = Column(Text)
    max_consecutive_wins = Column(Integer)
    max_consecutive_losses = Column(Integer)
    avg_hold_time_hours = Column(Float)
    exit_reasons = Column(JSON)

    run = relationship("Run", back_populates="result")


class RunTimeseries(Base):
    __tablename__ = "run_timeseries"

    run_id = Column(Integer, ForeignKey("runs.id"), primary_key=True)
    equity_curve = Column(LargeBinary)  # zlib(JSON[{date, balance}])
    drawdown_curve = Column(LargeBinary)  # zlib(JSON[{date, drawdown}])
    monthly_returns = Column(JSON)
    dispersion_range = Column(LargeBinary, nullable=True)  # zlib(JSON[{date, min, max}]) — batch only
    benchmark_curve = Column(LargeBinary, nullable=True)  # zlib(JSON[{date, balance}]) — buy-and-hold

    run = relationship("Run", back_populates="timeseries")


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False)
    symbol = Column(Text, nullable=False)
    side = Column(Text, nullable=False)
    entry_time = Column(DateTime, nullable=False)
    exit_time = Column(DateTime)
    hold_time_hours = Column(Float)
    entry_price = Column(Text, nullable=False)
    exit_price = Column(Text)
    stop_loss_price = Column(Text)
    tp1_price = Column(Text)
    tp2_price = Column(Text)
    tp3_price = Column(Text)
    quantity = Column(Text, nullable=False)
    size_usd = Column(Text, nullable=False)
    pnl = Column(Text)
    pnl_pct = Column(Float)
    exit_reason = Column(Text)
    note = Column(Text)

    run = relationship("Run", back_populates="trades")

    __table_args__ = (
        Index("idx_trades_run", "run_id"),
        Index("idx_trades_symbol", "symbol"),
    )


class Preset(Base):
    __tablename__ = "presets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(Text, nullable=False)
    strategy = Column(Text, nullable=False, index=True)
    config = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("name", "strategy", name="uq_preset_name_strategy"),
    )


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(Integer, ForeignKey("runs.id"), nullable=False)
    name = Column(Text, nullable=False)
    color = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    run = relationship("Run", back_populates="tags")

    __table_args__ = (
        UniqueConstraint("run_id", "name"),
        Index("idx_tags_run", "run_id"),
        Index("idx_tags_name", "name"),
    )


class SignalReplayRun(Base):
    """Immutable provenance and status for one BTC M5/M15 signal replay."""

    __tablename__ = "signal_replay_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    status = Column(Text, nullable=False, default="running")
    strategy_name = Column(Text, nullable=False, default="btc_rsi_cross_alert")
    definition_version = Column(Text, nullable=False)
    git_hash = Column(Text)
    symbol = Column(Text, nullable=False)
    requested_start_at = Column(DateTime)
    requested_end_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    source_metadata = Column(JSON, nullable=False, default=dict)
    counters = Column(JSON, nullable=False, default=dict)
    error_message = Column(Text)

    signals = relationship(
        "SignalReplaySignal",
        back_populates="replay_run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("idx_signal_replay_runs_created", "created_at"),
        Index("idx_signal_replay_runs_status", "status"),
    )


class SignalReplaySignal(Base):
    """Immutable structured snapshot of one confirmed replay signal."""

    __tablename__ = "replay_signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    replay_run_id = Column(
        Integer,
        ForeignKey("signal_replay_runs.id"),
        nullable=False,
    )
    event_id = Column(Text, nullable=False)
    sequence = Column(Integer, nullable=False)
    timeframe = Column(Text, nullable=False)
    definition_version = Column(Text, nullable=False)
    trigger_open_at = Column(DateTime, nullable=False)
    trigger_close_at = Column(DateTime, nullable=False)
    trigger_close_price = Column(Text, nullable=False)
    trigger_price_ema21 = Column(Text, nullable=False)
    rsi21 = Column(Float, nullable=False)
    rsi_ema9 = Column(Float, nullable=False)
    rsi_wma45 = Column(Float, nullable=False)
    rsi_spread = Column(Float, nullable=False)
    previous_rsi_ema9 = Column(Float)
    previous_rsi_wma45 = Column(Float)
    h4_close_price = Column(Text, nullable=False)
    h4_price_ema21 = Column(Text, nullable=False)
    h4_close_at = Column(DateTime, nullable=False)
    decision_reason = Column(Text, nullable=False)
    telegram_card = Column(Text, nullable=False)
    snapshot = Column(JSON, nullable=False)

    replay_run = relationship("SignalReplayRun", back_populates="signals")
    review = relationship(
        "SignalReview",
        back_populates="signal",
        uselist=False,
        cascade="all, delete-orphan",
    )
    forward_metrics = relationship(
        "SignalForwardMetric",
        back_populates="signal",
        cascade="all, delete-orphan",
        order_by="SignalForwardMetric.horizon_minutes",
    )

    __table_args__ = (
        UniqueConstraint(
            "replay_run_id",
            "event_id",
            name="uq_signal_replay_signal_run_event",
        ),
        Index("idx_replay_signals_timeframe", "timeframe"),
        Index("idx_replay_signals_trigger_close", "trigger_close_at"),
        Index("idx_replay_signals_event", "event_id"),
    )


class SignalReview(Base):
    """Latest single-operator quality/outcome review for one signal."""

    __tablename__ = "signal_reviews"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(
        Integer,
        ForeignKey("replay_signals.id"),
        nullable=False,
        unique=True,
    )
    quality = Column(Text, nullable=False, default="UNREVIEWED")
    human_outcome = Column(Text, nullable=False, default="UNSET")
    note = Column(Text)
    reviewed_at = Column(DateTime)
    updated_at = Column(DateTime, default=datetime.utcnow)
    future_unlocked_at = Column(DateTime)

    signal = relationship("SignalReplaySignal", back_populates="review")

    __table_args__ = (
        Index("idx_signal_reviews_quality", "quality"),
        Index("idx_signal_reviews_outcome", "human_outcome"),
    )


class SignalForwardMetric(Base):
    """Objective close-return and excursion observation for one horizon."""

    __tablename__ = "signal_forward_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_id = Column(
        Integer,
        ForeignKey("replay_signals.id"),
        nullable=False,
    )
    horizon_minutes = Column(Integer, nullable=False)
    price_at_observation = Column(Text)
    return_pct = Column(Float)
    mfe_pct = Column(Float)
    mae_pct = Column(Float)
    observed_at = Column(DateTime)
    complete = Column(Boolean, nullable=False, default=False)
    warning = Column(Text)

    signal = relationship("SignalReplaySignal", back_populates="forward_metrics")

    __table_args__ = (
        UniqueConstraint(
            "signal_id",
            "horizon_minutes",
            name="uq_signal_forward_metric_signal_horizon",
        ),
        Index("idx_signal_forward_metrics_signal", "signal_id"),
    )

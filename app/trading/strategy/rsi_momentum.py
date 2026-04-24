# app/trading/strategy/rsi_momentum.py
"""
RsiMomentumStrategy — SHORT entries only.

Entry conditions (all must hold simultaneously):
  S1: EMA9 crossed below WMA45 on this candle *OR* alignment still holds
      from a previous crossover candle (flexible persistence, capped by
      ``max_candles_since_crossover``).
  S2: RSI < EMA9
  S3: EMA9 < WMA45
  S4: (WMA45 - EMA9) > spread_threshold  (default 2.5)
  S5: Bearish RSI divergence in last 30 candles
  S6: Trend filter — ``close < EMA200`` (disable with ``ema200_filter=False``)

Exit system:
  - Dual SL: soft SL at 30-candle highest high, disaster SL at 3x distance
  - Multi-TP: configurable R:R ratios (default TP1 1R, TP2 2R, TP3 3R)
  - Lock-profit: move SL to +0.5R after price drops 1.0R (inverted for shorts)
  - Stale-trade exit: force close after ``stale_exit_candles`` candles if TP1
    has not been hit (BE close if already in profit, market close otherwise).

Config lives in the RsiMomentumConfig dataclass in this file (NOT config.yaml).

Entry logic: see rsi_momentum_entry.py
Exit logic:  see rsi_momentum_exit.py
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import fields as dc_fields
from decimal import Decimal

import pandas as pd
import structlog

from app.core.actions import DoNothing
from app.core.analysis_result import AnalysisResult
from app.core.constants import DEFAULT_MAKER_FEE, DEFAULT_TAKER_FEE
from app.core.context import SCANNING
from app.core.snapshots import ContextSnapshot, PositionSnapshot
from app.data.indicators import Indicators
from app.trading.strategy.base import BaseStrategy
from app.trading.strategy.rsi_momentum_entry import check_entry
from app.trading.strategy.rsi_momentum_exit import manage_exit
from app.trading.strategy.utils.config_helpers import merge_config
from app.trading.strategy.utils.param_metadata import (
    RSI_MOMENTUM_GROUPS,
    RSI_MOMENTUM_METADATA,
)
from app.trading.strategy.utils.schema_helper import SchemaConfigMixin

logger = structlog.get_logger()


@dataclass(frozen=True)
class RsiMomentumConfig(SchemaConfigMixin):
    """Typed config for RsiMomentumStrategy. Uses sensible defaults."""

    METADATA = RSI_MOMENTUM_METADATA
    UI_GROUPS = RSI_MOMENTUM_GROUPS

    # Indicator params
    rsi_period: int = 14
    ema_period: int = 9
    wma_period: int = 45
    price_ema_slow: int = 200  # S6: EMA200 trend filter period

    # Entry conditions
    spread_threshold: float = 2.5  # S4: min (WMA45 - EMA9) distance
    divergence_lookback: int = 30  # S5: candles to search for divergence
    pivot_strength: int = 5  # S5: N for 11-bar pivot (N on each side)
    min_candles: int = 210  # Warm-up: EMA200 + 45 WMA + buffer
    ema200_filter: bool = True  # S6: require close < EMA200 before shorting
    max_candles_since_crossover: int = 3  # S1: cap how long a crossover stays valid

    # Exit: SL
    sl_lookback: int = 30  # Highest high lookback for soft SL
    disaster_sl_multiplier: float = 3.0  # Hard SL = entry + 3x soft_sl_distance

    # Exit: TP
    tp1_rr: float = 1.0
    tp2_rr: float = 2.0
    tp3_rr: float = 3.0
    tp_count: int = 3
    tp1_close_pct: float = 0.50
    tp2_close_pct: float = 0.50
    # TP3 closes all remaining

    # Exit: Lock profit
    # Defaults loosened (from 0.5/0.2) after post-trade review: lock kicks in
    # only once -1R is reached and parks SL at -0.5R, to avoid BE sweeps.
    move_sl_rr: float = 1.0  # Trigger: move SL when price drops 1.0R (short)
    lock_profit_rr: float = 0.5  # New SL level: 0.5R below entry (lock profit)

    # Exit: Stale trade
    # Force exit if TP1 has not been hit after N candles. BE close when
    # already in profit (avoids donating it back), market close otherwise.
    # Set to 0 to disable.
    stale_exit_candles: int = 8

    # Fees
    taker_fee: float = DEFAULT_TAKER_FEE
    maker_fee: float = DEFAULT_MAKER_FEE

    # Trade management
    use_active_trades: bool = True
    candle_close_slippage_pct: float = 0.0


class RsiMomentumStrategy(BaseStrategy):
    """
    RSI Momentum strategy — SHORT entries only.

    Entry: S1-S5 (see module docstring).
    Exit:  Dual SL + multi-TP + lock-profit.

    Signal persistence: enter on the exact crossover candle OR on any
    subsequent candle as long as full alignment (S2+S3+S4) still holds
    and the crossover_detected flag is set in context.
    """

    CONFIG_CLASS = RsiMomentumConfig

    DEFAULT_CONFIG = {
        f.name: f.default for f in dc_fields(RsiMomentumConfig)
    }

    def __init__(self, config: dict):
        super().__init__(config)

        # Accept either an AppConfig object or a raw dict. Extract strategy
        # overrides from the conventional strategy_params nested dict; fall
        # back to top-level fields for backwards compatibility.
        from app.core.config import AppConfig

        if isinstance(config, AppConfig):
            overrides = dict(getattr(config, "strategy_params", {}) or {})
        elif isinstance(config, dict):
            overrides = dict(config.get("strategy_params") or {})
            # Top-level keys that happen to match a config field are honoured
            # too (used by some call sites that pass a flat dict).
            top_level_names = {f.name for f in dc_fields(RsiMomentumConfig)}
            for k, v in config.items():
                if k in top_level_names and k not in overrides:
                    overrides[k] = v
        else:
            overrides = {}

        self.cfg = merge_config(RsiMomentumConfig, overrides) if overrides else RsiMomentumConfig()
        self.indicators = Indicators(
            rsi_period=self.cfg.rsi_period,
            rsi_ema_period=self.cfg.ema_period,
            rsi_wma_period=self.cfg.wma_period,
            price_ema_slow=self.cfg.price_ema_slow,
            include_price_emas=True,
        )
        self.taker_fee = Decimal(str(self.cfg.taker_fee))
        self.maker_fee = Decimal(str(self.cfg.maker_fee))

    def analyze(
        self,
        symbol: str,
        df: pd.DataFrame,
        position: PositionSnapshot | None = None,
        context: ContextSnapshot | None = None,
    ) -> AnalysisResult:
        if context is None:
            context = ContextSnapshot(state=SCANNING)

        _noop = AnalysisResult(actions=[DoNothing()], new_context=context)

        # -- Warm-up check
        if df is None or len(df) < self.cfg.min_candles:
            logger.debug(
                "rsi_momentum.warmup",
                symbol=symbol,
                candles=len(df) if df is not None else 0,
                required=self.cfg.min_candles,
            )
            return _noop

        # Compute indicators
        df_ind = self.indicators.compute(df)

        # -- EXIT management (position open)
        if self.cfg.use_active_trades and position and position.has_position:
            return manage_exit(
                symbol,
                df_ind,
                position,
                context,
                move_sl_rr=self.cfg.move_sl_rr,
                lock_profit_rr=self.cfg.lock_profit_rr,
                stale_exit_candles=self.cfg.stale_exit_candles,
                taker_fee=self.taker_fee,
                maker_fee=self.maker_fee,
            )

        # -- ENTRY logic (no position)
        return check_entry(
            symbol,
            df_ind,
            context,
            cfg=self.cfg,
            indicators=self.indicators,
            taker_fee=self.taker_fee,
            maker_fee=self.maker_fee,
        )

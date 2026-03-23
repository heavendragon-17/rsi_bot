# app/trading/strategy/rsi_momentum.py
"""
RsiMomentumStrategy — SHORT entries only.

Entry conditions (all must hold simultaneously):
  S1: EMA9 crossed below WMA45 on this candle *OR* alignment still holds
      from a previous crossover candle (flexible persistence).
  S2: RSI < EMA9
  S3: EMA9 < WMA45
  S4: (WMA45 - EMA9) > spread_threshold  (default 2.5)
  S5: Bearish RSI divergence in last 30 candles

Exit system:
  - Dual SL: soft SL at 30-candle highest high, disaster SL at 3x distance
  - Multi-TP: configurable R:R ratios (default TP1 1R, TP2 2R, TP3 3R)
  - Lock-profit: move SL to +0.2R after price drops 0.5R (inverted for shorts)

Config lives in the RsiMomentumConfig dataclass in this file (NOT config.yaml).

Entry logic: see rsi_momentum_entry.py
Exit logic:  see rsi_momentum_exit.py
"""

from __future__ import annotations

from dataclasses import dataclass, fields as dc_fields
from decimal import Decimal

import pandas as pd
import structlog

from app.core.actions import DoNothing
from app.core.constants import DEFAULT_MAKER_FEE, DEFAULT_TAKER_FEE
from app.core.analysis_result import AnalysisResult
from app.core.context import SCANNING
from app.core.snapshots import ContextSnapshot, PositionSnapshot
from app.data.indicators import Indicators
from app.trading.strategy.base import BaseStrategy
from app.trading.strategy.rsi_momentum_entry import check_entry
from app.trading.strategy.rsi_momentum_exit import manage_exit
from app.trading.strategy.utils.config_helpers import merge_config

logger = structlog.get_logger()


@dataclass(frozen=True)
class RsiMomentumConfig:
    """Typed config for RsiMomentumStrategy. Uses sensible defaults."""

    # Indicator params
    rsi_period: int = 14
    ema_period: int = 9
    wma_period: int = 45

    # Entry conditions
    spread_threshold: float = 2.5  # S4: min (WMA45 - EMA9) distance
    divergence_lookback: int = 30  # S5: candles to search for divergence
    pivot_strength: int = 5  # S5: N for 11-bar pivot (N on each side)
    min_candles: int = 75  # Warm-up: 14 RSI + 45 WMA + 16 buffer

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
    move_sl_rr: float = 0.5  # Trigger: move SL when price drops 0.5R (short)
    lock_profit_rr: float = 0.2  # New SL level: 0.2R below entry (lock profit)

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

    DEFAULT_CONFIG = {
        f.name: f.default for f in dc_fields(RsiMomentumConfig)
    }

    def __init__(self, config: dict):
        super().__init__(config)
        self.cfg = merge_config(RsiMomentumConfig, config) if config else RsiMomentumConfig()
        self.indicators = Indicators(
            rsi_period=self.cfg.rsi_period,
            rsi_ema_period=self.cfg.ema_period,
            rsi_wma_period=self.cfg.wma_period,
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

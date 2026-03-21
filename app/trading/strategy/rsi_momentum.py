# app/strategies/rsi_momentum.py
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
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Dict, Optional

import pandas as pd
import structlog

from app.trading.strategy.base import BaseStrategy
from app.trading.strategy.utils.config_helpers import merge_config
from app.trading.strategy.utils.trade_state import TradeState
from app.trading.strategy.utils.sl_tp_builders import build_tp_allocations
from app.data.indicators import Indicators
from app.trading.sl_tp_calculator import SLTPCalculator
from app.core.context import SCANNING
from app.core.snapshots import PositionSnapshot, ContextSnapshot
from app.core.analysis_result import AnalysisResult
from app.core.actions import (
    OpenPosition, ClosePosition, MoveSL, DoNothing,
    SIDE_SELL, EXIT_CLOSE_BY_CANDLE_SL,
    DEFAULT_TAKER_FEE, DEFAULT_MAKER_FEE,
)
from app.core.utils import to_decimal_or_none

logger = structlog.get_logger()


@dataclass(frozen=True)
class RsiMomentumConfig:
    """Typed config for RsiMomentumStrategy. Uses sensible defaults."""

    # Indicator params
    rsi_period: int = 14
    ema_period: int = 9
    wma_period: int = 45

    # Entry conditions
    spread_threshold: float = 2.5       # S4: min (WMA45 - EMA9) distance
    divergence_lookback: int = 30       # S5: candles to search for divergence
    pivot_strength: int = 5             # S5: N for 11-bar pivot (N on each side)
    min_candles: int = 75               # Warm-up: 14 RSI + 45 WMA + 16 buffer

    # Exit: SL
    sl_lookback: int = 30               # Highest high lookback for soft SL
    disaster_sl_multiplier: float = 3.0 # Hard SL = entry + 3× soft_sl_distance

    # Exit: TP
    tp1_rr: float = 1.0
    tp2_rr: float = 2.0
    tp3_rr: float = 3.0
    tp_count: int = 3
    tp1_close_pct: float = 0.50
    tp2_close_pct: float = 0.50
    # TP3 closes all remaining

    # Exit: Lock profit
    move_sl_rr: float = 0.5         # Trigger: move SL when price drops 0.5R (short)
    lock_profit_rr: float = 0.2     # New SL level: 0.2R below entry (lock profit)

    # Fees
    taker_fee: float = DEFAULT_TAKER_FEE
    maker_fee: float = DEFAULT_MAKER_FEE

    # Trade management
    use_active_trades: bool = True
    candle_close_slippage_pct: float = 0.0

    # TradeState and merge_config imported from app.trading.strategy.utils


class RsiMomentumStrategy(BaseStrategy):
    """
    RSI Momentum strategy — SHORT entries only.

    Entry: S1–S5 (see module docstring).
    Exit:  Dual SL + multi-TP + lock-profit.

    Signal persistence: enter on the exact crossover candle OR on any
    subsequent candle as long as full alignment (S2+S3+S4) still holds
    and the crossover_detected flag is set in context.
    """

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

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    # ------------------------------------------------------------------
    # Main analysis entry point
    # ------------------------------------------------------------------

    def analyze(
        self,
        symbol: str,
        df: pd.DataFrame,
        position: Optional[PositionSnapshot] = None,
        context: Optional[ContextSnapshot] = None,
    ) -> AnalysisResult:
        if context is None:
            context = ContextSnapshot(state=SCANNING)

        _noop = AnalysisResult(actions=[DoNothing()], new_context=context)

        # ── Warm-up check ──────────────────────────────────────────────
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

        # ── EXIT management (position open) ────────────────────────────
        if self.cfg.use_active_trades and position and position.has_position:
            return self._manage_exit(symbol, df_ind, position, context)

        # ── ENTRY logic (no position) ──────────────────────────────────
        return self._check_entry(symbol, df_ind, context)

    # ------------------------------------------------------------------
    # Exit management (short position open)
    # ------------------------------------------------------------------

    def _manage_exit(
        self,
        symbol: str,
        df_ind: pd.DataFrame,
        position: PositionSnapshot,
        context: ContextSnapshot,
    ) -> AnalysisResult:
        ts = TradeState.from_meta(context.meta)

        entry_price = to_decimal_or_none(ts.entry_price)
        if entry_price is None:
            return AnalysisResult(actions=[DoNothing()], new_context=context)

        soft_sl = context.soft_sl_price or to_decimal_or_none(ts.soft_sl_price)
        original_soft_sl = to_decimal_or_none(ts.original_soft_sl) or soft_sl
        moved_sl = ts.moved_sl_to_entry
        pending_candle_sl = ts.pending_candle_sl
        lock_profit_price = to_decimal_or_none(ts.lock_profit_price)

        last = df_ind.iloc[-1]
        close = to_decimal_or_none(last.get("close"))
        low = to_decimal_or_none(last.get("low"))
        open_price = to_decimal_or_none(last.get("open"))

        if lock_profit_price is None and original_soft_sl and entry_price:
            # Compute lock-profit level from original soft SL distance
            lock_profit_price = SLTPCalculator.compute_lock_profit_price(
                entry_price=entry_price,
                soft_sl_price=original_soft_sl,
                side=SIDE_SELL,
                lock_profit_rr=Decimal(str(self.cfg.lock_profit_rr)),
                taker_fee=self.taker_fee,
            )

        # ── STEP 0: pending candle SL — close at this candle's open ───
        if pending_candle_sl and open_price is not None:
            return AnalysisResult(
                actions=[ClosePosition(symbol=symbol, reason=EXIT_CLOSE_BY_CANDLE_SL, price=open_price)],
                new_context=ContextSnapshot(state=SCANNING),
            )

        # ── STEP 1: Move SL to lock-profit when price drops to trigger ─
        # For SHORT: price going DOWN is profitable → trigger when low <= move_trigger
        if not moved_sl and low is not None and soft_sl is not None and original_soft_sl is not None:
            move_trigger = to_decimal_or_none(ts.move_trigger)
            if move_trigger is None:
                # Fallback: compute if not cached (e.g. older context)
                move_trigger = SLTPCalculator.compute_tp_price(
                    entry_price=entry_price,
                    sl_price=original_soft_sl,
                    side=SIDE_SELL,
                    rr_ratio=Decimal(str(self.cfg.move_sl_rr)),
                    taker_fee=self.taker_fee,
                    exit_fee=self.maker_fee,
                )
            if move_trigger is not None and low <= move_trigger and lock_profit_price is not None:
                new_ts = TradeState.from_meta(context.meta)
                new_ts.moved_sl_to_entry = True
                new_ts.sl_price = lock_profit_price
                new_ts.soft_sl_price = lock_profit_price
                new_ctx = ContextSnapshot(
                    state=context.state,
                    soft_sl_price=lock_profit_price,
                    meta=new_ts.to_meta(),
                )
                return AnalysisResult(
                    actions=[MoveSL(
                        symbol=symbol,
                        new_sl_price=lock_profit_price,
                        reason=f"MOVE_SL_LOCK_PROFIT (low={low} <= {move_trigger} = -{self.cfg.move_sl_rr}R, new_sl={lock_profit_price} = -{self.cfg.lock_profit_rr}R)",
                    )],
                    new_context=new_ctx,
                )

        # ── STEP 2: Candle-close SL — flag exit for next candle ───────
        # For SHORT: close >= soft_sl means price went AGAINST us (up)
        if soft_sl is not None and close is not None and close >= soft_sl:
            new_ts = TradeState.from_meta(context.meta)
            new_ts.pending_candle_sl = True
            new_ctx = ContextSnapshot(state=context.state, soft_sl_price=soft_sl, meta=new_ts.to_meta())
            return AnalysisResult(actions=[DoNothing()], new_context=new_ctx)

        return AnalysisResult(actions=[DoNothing()], new_context=context)

    # ------------------------------------------------------------------
    # Entry logic
    # ------------------------------------------------------------------

    def _check_entry(
        self,
        symbol: str,
        df_ind: pd.DataFrame,
        context: ContextSnapshot,
    ) -> AnalysisResult:
        ts = TradeState.from_meta(context.meta)
        _noop = AnalysisResult(actions=[DoNothing()], new_context=context)

        # ── S2 + S3: Alignment check ────────────────────────────────────
        if not self.indicators.check_alignment(df_ind, direction="bearish"):
            # Alignment broken → reset crossover flag
            if ts.crossover_detected:
                ts.crossover_detected = False
                return AnalysisResult(
                    actions=[DoNothing()],
                    new_context=ContextSnapshot(state=SCANNING, meta=ts.to_meta()),
                )
            return _noop

        # ── S1: Crossover or persistent alignment ───────────────────────
        crossover_now = self.indicators.detect_crossover(df_ind, direction="bearish")
        crossover_before = ts.crossover_detected

        if not crossover_now and not crossover_before:
            return _noop

        # ── S4: Spread constraint ────────────────────────────────────────
        last = df_ind.iloc[-1]
        ema = last.get("rsi_ema9")
        wma = last.get("rsi_wma45")
        if ema is None or wma is None or pd.isna(ema) or pd.isna(wma):
            return _noop

        spread = float(wma) - float(ema)
        if spread <= self.cfg.spread_threshold:
            return _noop

        # ── S5: Bearish RSI divergence ───────────────────────────────────
        if not self.indicators.detect_bearish_divergence(
            df_ind,
            lookback=self.cfg.divergence_lookback,
            pivot_strength=self.cfg.pivot_strength,
        ):
            # Preserve crossover flag so persistence still works
            ts.crossover_detected = crossover_now or crossover_before
            return AnalysisResult(
                actions=[DoNothing()],
                new_context=ContextSnapshot(state=SCANNING, meta=ts.to_meta()),
            )

        # ── All conditions met — compute SL/TP ──────────────────────────
        close = to_decimal_or_none(last.get("close"))
        if close is None:
            return _noop

        entry_price = close

        # Soft SL: highest high of last sl_lookback candles
        soft_sl = SLTPCalculator.compute_soft_sl(
            df_ind, side=SIDE_SELL, lookback=self.cfg.sl_lookback
        )
        if soft_sl is None:
            logger.warning("rsi_momentum.no_soft_sl", symbol=symbol)
            return _noop

        # Zero risk distance → skip
        if soft_sl <= entry_price:
            logger.info(
                "rsi_momentum.zero_risk_distance",
                symbol=symbol,
                entry=str(entry_price),
                soft_sl=str(soft_sl),
            )
            return _noop

        # Disaster SL
        disaster_sl = SLTPCalculator.compute_disaster_sl(
            entry_price=entry_price,
            soft_sl_price=soft_sl,
            side=SIDE_SELL,
            multiplier=Decimal(str(self.cfg.disaster_sl_multiplier)),
        )

        # TP prices (limit orders → maker fee for exit)
        tp_rrs = [self.cfg.tp1_rr, self.cfg.tp2_rr, self.cfg.tp3_rr]
        tp_prices_all = []
        for rr in tp_rrs[:self.cfg.tp_count]:
            tp = SLTPCalculator.compute_tp_price(
                entry_price=entry_price,
                sl_price=soft_sl,
                side=SIDE_SELL,
                rr_ratio=Decimal(str(rr)),
                taker_fee=self.taker_fee,
                exit_fee=self.maker_fee,
            )
            if tp is not None:
                tp_prices_all.append(tp)

        if not tp_prices_all:
            return _noop

        # TP allocations
        tp_allocations = build_tp_allocations(
            self.cfg.tp_count, self.cfg.tp1_close_pct, self.cfg.tp2_close_pct
        )

        # Lock-profit price (stop_market → taker fee)
        lock_profit_price = SLTPCalculator.compute_lock_profit_price(
            entry_price=entry_price,
            soft_sl_price=soft_sl,
            side=SIDE_SELL,
            lock_profit_rr=Decimal(str(self.cfg.lock_profit_rr)),
            taker_fee=self.taker_fee,
        )

        # Pre-compute move_trigger so _manage_exit doesn't recompute every candle
        move_trigger = SLTPCalculator.compute_tp_price(
            entry_price=entry_price,
            sl_price=soft_sl,
            side=SIDE_SELL,
            rr_ratio=Decimal(str(self.cfg.move_sl_rr)),
            taker_fee=self.taker_fee,
            exit_fee=self.maker_fee,
        )

        # Build new context for the trade
        new_ts = TradeState(
            entry_price=entry_price,
            sl_price=soft_sl,
            soft_sl_price=soft_sl,
            original_soft_sl=soft_sl,
            disaster_sl_price=disaster_sl,
            lock_profit_price=lock_profit_price,
            move_trigger=move_trigger,
            tp_allocations=tp_allocations,
        )
        new_ctx = ContextSnapshot(
            state=SCANNING,
            soft_sl_price=soft_sl,
            meta=new_ts.to_meta(),
        )

        logger.info(
            "rsi_momentum.short_signal",
            symbol=symbol,
            entry=str(entry_price),
            soft_sl=str(soft_sl),
            disaster_sl=str(disaster_sl),
            tp1=str(tp_prices_all[0]) if tp_prices_all else None,
            spread=round(spread, 3),
        )

        return AnalysisResult(
            actions=[OpenPosition(
                symbol=symbol,
                side=SIDE_SELL,
                entry_price=entry_price,
                sl_price=disaster_sl,
                soft_sl_price=soft_sl,
                tp_prices=tp_prices_all,
                tp_allocations=tp_allocations,
                lock_profit_price=lock_profit_price,
                signal_class=1,
                reason=f"RSI_MOMENTUM SHORT (spread={spread:.2f} > {self.cfg.spread_threshold})",
            )],
            new_context=new_ctx,
        )

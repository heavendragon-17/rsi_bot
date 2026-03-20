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

from dataclasses import dataclass, field, fields as dc_fields
from decimal import Decimal
from typing import Any, Dict, Optional

import pandas as pd
import structlog

from app.strategies.base import BaseStrategy
from app.utils.crossover_indicators import CrossoverIndicators
from app.core.sl_tp_calculator import SLTPCalculator
from app.core.context import SCANNING
from app.core.snapshots import PositionSnapshot, ContextSnapshot
from app.core.analysis_result import AnalysisResult
from app.core.actions import (
    OpenPosition, ClosePosition, MoveSL, DoNothing,
    SIDE_SELL, EXIT_CLOSE_BY_CANDLE_SL,
)
from app.core.constants import DEFAULT_TAKER_FEE, DEFAULT_MAKER_FEE

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

    @classmethod
    def from_dict(cls, params: dict) -> "RsiMomentumConfig":
        valid = {f.name for f in dc_fields(cls)}
        return cls(**{k: v for k, v in params.items() if k in valid})


@dataclass
class TradeState:
    """Typed trade state stored in ContextSnapshot.meta.

    Replaces raw dict access with explicit fields to prevent typos
    and make the meta schema discoverable.
    """
    entry_price: Optional[Decimal] = None
    sl_price: Optional[Decimal] = None
    soft_sl_price: Optional[Decimal] = None
    original_soft_sl: Optional[Decimal] = None
    disaster_sl_price: Optional[Decimal] = None
    lock_profit_price: Optional[Decimal] = None
    move_trigger: Optional[Decimal] = None
    moved_sl_to_entry: bool = False
    pending_candle_sl: bool = False
    crossover_detected: bool = False
    tp_allocations: Optional[dict] = field(default_factory=dict)

    def to_meta(self) -> Dict[str, Any]:
        """Serialize to a plain dict for ContextSnapshot.meta."""
        return {
            "entry_price": self.entry_price,
            "sl_price": self.sl_price,
            "soft_sl_price": self.soft_sl_price,
            "original_soft_sl": self.original_soft_sl,
            "disaster_sl_price": self.disaster_sl_price,
            "lock_profit_price": self.lock_profit_price,
            "move_trigger": self.move_trigger,
            "moved_sl_to_entry": self.moved_sl_to_entry,
            "pending_candle_sl": self.pending_candle_sl,
            "crossover_detected": self.crossover_detected,
            "tp_allocations": self.tp_allocations,
        }

    @classmethod
    def from_meta(cls, meta: Optional[Dict[str, Any]]) -> "TradeState":
        """Deserialize from ContextSnapshot.meta dict."""
        if not meta:
            return cls()
        return cls(
            entry_price=meta.get("entry_price"),
            sl_price=meta.get("sl_price"),
            soft_sl_price=meta.get("soft_sl_price"),
            original_soft_sl=meta.get("original_soft_sl"),
            disaster_sl_price=meta.get("disaster_sl_price"),
            lock_profit_price=meta.get("lock_profit_price"),
            move_trigger=meta.get("move_trigger"),
            moved_sl_to_entry=bool(meta.get("moved_sl_to_entry", False)),
            pending_candle_sl=bool(meta.get("pending_candle_sl", False)),
            crossover_detected=bool(meta.get("crossover_detected", False)),
            tp_allocations=meta.get("tp_allocations"),
        )


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
        self.cfg = RsiMomentumConfig.from_dict(config) if config else RsiMomentumConfig()
        self.indicators = CrossoverIndicators(
            rsi_period=self.cfg.rsi_period,
            rsi_ema_period=self.cfg.ema_period,
            rsi_wma_period=self.cfg.wma_period,
        )
        self.taker_fee = Decimal(str(self.cfg.taker_fee))
        self.maker_fee = Decimal(str(self.cfg.maker_fee))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _to_dec(self, x) -> Optional[Decimal]:
        if x is None:
            return None
        return x if isinstance(x, Decimal) else Decimal(str(x))

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

        entry_price = self._to_dec(ts.entry_price)
        if entry_price is None:
            return AnalysisResult(actions=[DoNothing()], new_context=context)

        soft_sl = context.soft_sl_price or self._to_dec(ts.soft_sl_price)
        original_soft_sl = self._to_dec(ts.original_soft_sl) or soft_sl
        moved_sl = ts.moved_sl_to_entry
        pending_candle_sl = ts.pending_candle_sl
        lock_profit_price = self._to_dec(ts.lock_profit_price)

        last = df_ind.iloc[-1]
        close = self._to_dec(last.get("close"))
        low = self._to_dec(last.get("low"))
        open_price = self._to_dec(last.get("open"))

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
            move_trigger = self._to_dec(ts.move_trigger)
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
        close = self._to_dec(last.get("close"))
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
        tp_allocations = {}
        if self.cfg.tp_count == 1:
            tp_allocations["TP1"] = 1.0
        elif self.cfg.tp_count == 2:
            tp_allocations["TP1"] = self.cfg.tp1_close_pct
            tp_allocations["TP2"] = 1.0
        else:
            tp_allocations["TP1"] = self.cfg.tp1_close_pct
            tp_allocations["TP2"] = self.cfg.tp2_close_pct
            tp_allocations["TP3"] = 1.0

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

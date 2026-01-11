# app/strategies/rsi_no_retest.py
"""
Layer 2: Core Logic - RSI No Retest Strategy
===================================================================================
LONG ONLY strategy with NO RSI retest requirement.

Idea
----
We want a clean "trend reset -> first reclaim" entry:

SCANNING:
  1) Detect a candle CLOSE above EMA21 (reclaim).
  2) Look back N candles (default 30) and verify we had a "long decrease / pullback"
     mostly BELOW EMA21:
       - allow up to `max_above_ema21_in_lookback` candles that closed above EMA21
       - if more than that -> treat as noise and skip
  3) If pullback condition passes -> move to CONFIRMING.

CONFIRMING:
  1) Confirm RSI momentum:
       RSI_EMA9 - RSI_WMA45 >= rsi_spread_min  (default 1.5)
  2) Place BUY at EMA21 price (limit-style intent via SignalEvent.price = ema21).
  3) SL = lowest wick (lowest low) of the lookback window.
  4) TP1: Risk:Reward = 1:1 (50% take profit)  -> Portfolio moves SL to entry
  5) TP2: RSI >= 70 (remaining 50%)

Notes
-----
- No cooldown / no waiting / no SL lock (consistent with your recent preference).
- This strategy emits:
    BUY: includes entry_price (ema21), sl_price, tp1_price, and tp2 trigger (rsi70) via meta.
    SELL: optional RSI overbought hard exit (default 80) if you want.
- You MUST call PortfolioManager.check_tp_levels / execute_partial_close every candle
  to actually realize TP1/TP2 logic. This strategy only supplies levels/meta.

Config keys (strategy:)
----------------------
rsi_period: 21
rsi_ema_length: 9
rsi_wma_length: 45
price_ema_fast: 21
price_ema_slow: 200

nr_lookback: 30
nr_max_above_ema21: 3
nr_rsi_spread_min: 1.5

nr_tp2_rsi: 70
nr_rsi_sell: 80   (optional hard exit)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Any, Tuple

import pandas as pd

from app.strategies.base import BaseStrategy
from app.utils.indicators import Indicators
from app.utils.resampler import resample_dataframe
from app.core.events import SignalEvent
from app.core.context import StrategyContext, SCANNING, CONFIRMING


class RsiNoRetestStrategy(BaseStrategy):
    def __init__(self, config: dict):
        super().__init__(config)

        # Ensure context exists
        if hasattr(self, "ctx") and not hasattr(self, "context"):
            self.context = self.ctx  # type: ignore[attr-defined]
        if not hasattr(self, "context"):
            self.context = StrategyContext()

        strategy_cfg = config.get("strategy", {})
        bot_cfg = config.get("bot", {})

        self.timeframe = bot_cfg.get("timeframe", "1h")

        self.indicators = Indicators(
            rsi_length=strategy_cfg.get("rsi_period", 21),
            rsi_ema_length=strategy_cfg.get("rsi_ema_length", 9),
            rsi_wma_length=strategy_cfg.get("rsi_wma_length", 45),
            price_ema_fast=strategy_cfg.get("price_ema_fast", 21),
            price_ema_slow=strategy_cfg.get("price_ema_slow", 200),
        )

        self.lookback = int(strategy_cfg.get("nr_lookback", 30))
        self.max_above_ema21_in_lookback = int(strategy_cfg.get("nr_max_above_ema21", 3))
        self.rsi_spread_min = float(strategy_cfg.get("nr_rsi_spread_min", 1.5))

        # TP/Exit logic knobs
        self.tp2_rsi = float(strategy_cfg.get("nr_tp2_rsi", 70.0))

        # Only one trade per symbol
        self.use_active_trades = bool(strategy_cfg.get("use_active_trades", True))

    # ----------------------------
    # helpers
    # ----------------------------
    def _get_trade_meta(self, symbol: str) -> dict:
        trade = self.context.get_trade(symbol)
        if trade is None:
            return {}
        if trade.meta is None:
            trade.meta = {}
        return trade.meta

    def _ts_from_last(self, df: pd.DataFrame, last: dict) -> Any:
        ts = last.get("ts")
        if ts is None:
            try:
                return df.index[-1]
            except Exception:
                return None
        return ts

    def _count_closes_above(self, closes: pd.Series, ema21s: pd.Series) -> int:
        return int((closes > ema21s).sum())

    def _lowest_wick(self, lows: pd.Series) -> Optional[Decimal]:
        if lows is None or len(lows) == 0:
            return None
        v = lows.min()
        if v is None:
            return None
        return Decimal(str(v))

    def _detect_reclaim_and_pullback(
        self, df_ind: pd.DataFrame
    ) -> Tuple[bool, Optional[Decimal], Optional[Decimal], Optional[int]]:
        """
        Returns:
          (ok, entry_price(ema21), stop_price(lowest wick lookback), above_count)
        """
        if len(df_ind) < self.lookback + 5:
            return (False, None, None, None)

        # current and previous row
        cur = df_ind.iloc[-1]
        prev = df_ind.iloc[-2]

        close = cur.get("close")
        ema21 = cur.get("ema21")
        prev_close = prev.get("close")
        prev_ema21 = prev.get("ema21")

        if close is None or ema21 is None or prev_close is None or prev_ema21 is None:
            return (False, None, None, None)

        # "reclaim": previous close <= ema21 AND current close > ema21
        reclaimed = (prev_close <= prev_ema21) and (close > ema21)
        if not reclaimed:
            return (False, None, None, None)

        # lookback window (excluding current candle)
        window = df_ind.iloc[-(self.lookback + 1) : -1]
        if window is None or len(window) < self.lookback:
            return (False, None, None, None)

        closes = window["close"]
        ema21s = window["ema21"]

        above_count = self._count_closes_above(closes, ema21s)
        if above_count > self.max_above_ema21_in_lookback:
            # too many above EMA21 candles => not a clean pullback
            return (False, None, None, above_count)

        # stop = lowest wick in the window
        if "low" not in window.columns:
            return (False, None, None, above_count)

        sl = self._lowest_wick(window["low"])
        entry = Decimal(str(ema21))
        return (True, entry, sl, above_count)

    # ----------------------------
    # main
    # ----------------------------
    def analyze(self, symbol: str, df) -> Optional[SignalEvent]:
        """
        SCANNING:
          - detect reclaim above EMA21 + pullback condition
          - then go CONFIRMING and store entry/sl candidate in state

        CONFIRMING:
          - check RSI spread: rsi_ema9 - rsi_wma45 >= rsi_spread_min
          - emit BUY at ema21 with SL at lowest wick of lookback
          - TP1 = entry + (entry - SL)   (RR 1:1)
          - TP2 is RSI-based (>= 70) tracked by portfolio/runner using meta
        """
        if df is None or len(df) < max(220, self.lookback + 10):
            return None

        # Only evaluate on closed candles
        if "closed" in df.columns and not bool(df.iloc[-1]["closed"]):
            return None

        key = f"{symbol}:{self.timeframe}"

        # Resample if needed (keep your hook available)
        # If your df is already at timeframe, resample_dataframe should be identity.
        df_tf = resample_dataframe(df, self.timeframe) if "timestamp" in getattr(df, "columns", []) else df

        df_ind = self.indicators.compute(df_tf, symbol=symbol, timeframe=self.timeframe)
        last = Indicators.last(df_ind)
        if not last:
            return None

        ts = self._ts_from_last(df_tf, last)

        rsi = last.get("rsi")
        rsi_ema9 = last.get("rsi_ema9")
        rsi_wma45 = last.get("rsi_wma45")

        close = last.get("close")
        if close is None:
            return None

        # ---------------------------------------
        # State machine
        # ---------------------------------------
        state = self.context.get_state(key)

        # STATE: SCANNING
        if state.phase == SCANNING:
            ok, entry_price, sl_price, above_count = self._detect_reclaim_and_pullback(df_ind)
            if not ok or entry_price is None or sl_price is None:
                return None

            # store candidates in state via state attributes dynamically
            # (context.SymbolState is a dataclass; we can attach attrs safely in Python)
            state.nr_entry_price = entry_price  # type: ignore[attr-defined]
            state.nr_sl_price = sl_price        # type: ignore[attr-defined]
            state.nr_above_count = above_count  # type: ignore[attr-defined]

            self.context.transition(
                key,
                CONFIRMING,
                reason=f"Reclaim EMA21 + pullback ok (above_count={above_count})",
                now_ts=ts,
            )
            return None

        # STATE: CONFIRMING
        if state.phase == CONFIRMING:
            # require stored prices
            entry_price = getattr(state, "nr_entry_price", None)
            sl_price = getattr(state, "nr_sl_price", None)
            if entry_price is None or sl_price is None:
                self.context.transition(key, SCANNING, reason="Missing cached entry/SL", now_ts=ts)
                return None

            if rsi is None or rsi_ema9 is None or rsi_wma45 is None:
                return None

            spread = float(rsi_ema9) - float(rsi_wma45)
            if spread < self.rsi_spread_min:
                return None

            # TP1 = 1:1 RR
            risk = entry_price - sl_price
            if risk <= Decimal("0"):
                self.context.transition(key, SCANNING, reason="Invalid risk (entry<=SL)", now_ts=ts)
                return None

            tp1_price = entry_price + risk  # RR 1:1

            # TP2 is RSI>=70 (not a price). We still can provide a reference price:
            # If your Indicators supports calculate_price_at_rsi, use it; else leave None.
            tp2_price = None
            try:
                tp2_price = self.indicators.calculate_price_at_rsi(df_ind, self.tp2_rsi)
            except Exception:
                tp2_price = None

            # Open trade in context (so strategy doesn't re-enter)
            if self.use_active_trades:
                self.context.open_trade(
                    symbol=symbol,
                    timeframe=self.timeframe,
                    side="LONG",
                    entry_price=float(entry_price),
                    meta={
                        "entry_price": entry_price,
                        "sl_price": sl_price,
                        "tp1_price": tp1_price,
                        "tp2_rsi": self.tp2_rsi,   # important: RSI-based TP2 trigger
                        "tp2_price": tp2_price,
                        "mode": "no_retest",
                        "rsi_spread": spread,
                    },
                    now_ts=ts,
                )

            # reset state immediately after emitting BUY
            self.context.transition(key, SCANNING, reason="BUY emitted, reset scan", now_ts=ts)

            return SignalEvent(
                symbol=symbol,
                signal_type="BUY",
                price=entry_price,
                timestamp=ts,
                reason=f"NO-RETEST BUY: reclaim EMA21 + RSI spread ok (spread={spread:.2f} >= {self.rsi_spread_min})",
                tp1_price=tp1_price,
                tp2_price=tp2_price,
                tp3_price=None,
                sl_price=sl_price,
                signal_class=2,
            )

        # Safety reset
        self.context.transition(key, SCANNING, reason="Unknown state reset", now_ts=ts)
        return None

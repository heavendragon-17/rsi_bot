# app/strategies/rsi_no_retest.py
"""
Layer 2: Core Logic - RSI No Retest Strategy (Entry reclaim EMA21)
==================================================================

Rules (as required):
- Entry: first candle closing > EMA21 (cross up)
- Must be preceded by a prolonged decline: majority of candles in lookback closed below EMA21
    + allow maximum max_above_ema21 candles closed above EMA21 (noise filter)
- RSI confirmation: (RSI_EMA9 - RSI_WMA45) >= rsi_spread_min
- SL: based on RSI_EMA9 (price at RSI = RSI_EMA9) [for tighter SL], with option to use lowest wick/close in lookback
    + Move SL to Entry when price reaches +0.5R (RR = 0.5)
- TP: 1:1 RR CLOSE ALL

No cooldown / no waiting / no SL lock
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Any

import pandas as pd

from app.strategies.base import BaseStrategy
from app.utils.indicators import Indicators
from app.utils.resampler import resample_dataframe
from app.core.events import SignalEvent
from app.core.context import StrategyContext, SCANNING, CONFIRMING


class RsiNoRetestStrategy(BaseStrategy):
    """
    RSI No Retest Strategy - enters on EMA21 reclaim without requiring RSI retest.
    """
    
    # Default configuration for this strategy
    DEFAULT_CONFIG = {
        # Indicator parameters
        "rsi_period": 21,
        "rsi_ema_length": 9,
        "rsi_wma_length": 45,
        "price_ema_fast": 21,
        "price_ema_slow": 200,
        
        # Entry conditions
        "nr_lookback": 30,           # Candles to check for pullback
        "nr_max_above_ema21": 1,     # Max candles above EMA21 in lookback (0 = strict)
        "nr_rsi_spread_min": 1.5,    # Min RSI_EMA9 - RSI_WMA45 spread
        
        # SL settings
        "nr_sl_mode": "lowest_close",    # "rsi_ema9" or "lowest_wick"
        "sl_buffer_pct": 0.0,        # No buffer for tight SL
        
        # TP settings
        "nr_tp_rr": 1,               # Risk:Reward ratio (1 = 1:1)
        
        # Trade management
        "use_active_trades": True,
    }

    def __init__(self, config: dict):
        super().__init__(config)

        # Ensure context exists
        if hasattr(self, "ctx") and not hasattr(self, "context"):
            self.context = self.ctx  # type: ignore[attr-defined]
        if not hasattr(self, "context"):
            self.context = StrategyContext()

        # Use strategy defaults, allow override from config
        cfg = {**self.DEFAULT_CONFIG, **config.get("strategy_params", {})}
        bot_cfg = config.get("bot", {})

        self.timeframe = bot_cfg.get("timeframe", "15m")

        self.indicators = Indicators(
            rsi_length=cfg.get("rsi_period", 14),
            rsi_ema_length=cfg.get("rsi_ema_length", 9),
            rsi_wma_length=cfg.get("rsi_wma_length", 45),
            price_ema_fast=cfg.get("price_ema_fast", 21),
            price_ema_slow=cfg.get("price_ema_slow", 200),
        )

        # ================================
        # Strategy parameters
        # ================================
        self.lookback = int(cfg.get("nr_lookback", 30))
        self.max_above_ema21 = int(cfg.get("nr_max_above_ema21", 1))
        self.rsi_spread_min = float(cfg.get("nr_rsi_spread_min", 1.5))

        # SL behavior
        # "rsi_ema9": SL = price_at_rsi(RSI_EMA9)
        # "lowest_wick": SL = min(low) lookback
        # "lowest_close": SL = min(close) lookback
        self.sl_mode = str(cfg.get("nr_sl_mode", "rsi_ema9")).lower()
        self.sl_buffer_pct = float(cfg.get("sl_buffer_pct", 0.0))

        # TP behavior
        self.tp_rr = Decimal(str(cfg.get("nr_tp_rr", 1)))  # 1:1

        # NEW: Move SL to Entry trigger (RR = 0.5)
        self.move_sl_rr = Decimal(str(cfg.get("nr_move_sl_rr", 0.5)))
        self.use_active_trades = bool(cfg.get("use_active_trades", True))

    # ---------------- helpers ----------------
    def _ts_from_last(self, df: pd.DataFrame, last: dict) -> Any:
        ts = last.get("ts")
        if ts is None:
            try:
                return df.index[-1]
            except Exception:
                return None
        return ts

    def _to_dec(self, x) -> Optional[Decimal]:
        if x is None:
            return None
        return x if isinstance(x, Decimal) else Decimal(str(x))

    def _detect_reclaim(self, df_ind: pd.DataFrame) -> bool:
        if len(df_ind) < 2:
            return False
        cur = df_ind.iloc[-1]
        prev = df_ind.iloc[-2]
        close = cur.get("close")
        ema21 = cur.get("ema21")
        prev_close = prev.get("close")
        prev_ema21 = prev.get("ema21")
        if close is None or ema21 is None or prev_close is None or prev_ema21 is None:
            return False
        return (prev_close <= prev_ema21) and (close > ema21)

    def _pullback_filter(self, df_ind: pd.DataFrame) -> bool:
        """
        Lookback excludes current candle.
        Condition: number of candles closed above EMA21 <= max_above_ema21
        """
        if len(df_ind) < self.lookback + 2:
            return False
        window = df_ind.iloc[-(self.lookback + 1) : -1]
        closes = window["close"]
        ema21s = window["ema21"]
        above = int((closes > ema21s).sum())
        return above <= self.max_above_ema21

    def _compute_sl(self, df_ind: pd.DataFrame) -> Optional[Decimal]:
        if self.sl_mode == "lowest_wick":
            window = df_ind.iloc[-(self.lookback + 1) : -1]
            if "low" not in window.columns:
                return None
            sl = self._to_dec(window["low"].min())
        elif self.sl_mode == "lowest_close":
            window = df_ind.iloc[-(self.lookback + 1) : -1]
            if "close" not in window.columns:
                return None
            sl = self._to_dec(window["close"].min())
        else:
            # SL = price_at_rsi(RSI_EMA9)
            last = Indicators.last(df_ind)
            if not last:
                return None
            rsi_ema9 = last.get("rsi_ema9")
            if rsi_ema9 is None:
                return None
            sl = self.indicators.calculate_price_at_rsi(df_ind, float(rsi_ema9))

        if sl is None:
            return None

        if self.sl_buffer_pct and self.sl_buffer_pct > 0:
            sl = sl * Decimal(str(1 - self.sl_buffer_pct))
        return sl

    def _compute_tp_1to1(self, entry: Decimal, sl: Decimal) -> Optional[Decimal]:
        risk = entry - sl
        if risk <= Decimal("0"):
            return None
        return entry + (risk * self.tp_rr)

    def _compute_price_at_rr(self, entry: Decimal, sl: Decimal, rr: Decimal) -> Optional[Decimal]:
        """
        For LONG:
          risk = entry - sl
          price_at_rr = entry + rr * risk
        """
        risk = entry - sl
        if risk <= Decimal("0"):
            return None
        return entry + (risk * rr)

    # ---------------- main ----------------
    def analyze(self, symbol: str, df) -> Optional[SignalEvent]:
        if df is None or len(df) < max(220, self.lookback + 10):
            return None

        if "closed" in df.columns and not bool(df.iloc[-1]["closed"]):
            return None

        key = f"{symbol}:{self.timeframe}"

        # optional resample hook
        df_tf = resample_dataframe(df, self.timeframe) if "timestamp" in getattr(df, "columns", []) else df

        df_ind = self.indicators.compute(df_tf, symbol=symbol, timeframe=self.timeframe)
        last = Indicators.last(df_ind)
        if not last:
            return None

        ts = self._ts_from_last(df_tf, last)

        # prices (Decimals)
        close = self._to_dec(last.get("close"))
        high = self._to_dec(last.get("high"))
        ema21 = self._to_dec(last.get("ema21"))

        if close is None or ema21 is None:
            return None

        # RSI values
        rsi_ema9 = last.get("rsi_ema9")
        rsi_wma45 = last.get("rsi_wma45")

        # -------------------------
        # EXIT / MANAGEMENT inside strategy:
        #  - Move SL to Entry at +0.5R (intrabar by HIGH)
        #  - TP 1:1 close all (intrabar by HIGH)
        # -------------------------
        if self.use_active_trades and self.context.has_active_trade(symbol):
            trade = self.context.get_trade(symbol)
            meta = trade.meta if trade and trade.meta else {}

            entry_price = meta.get("entry_price")
            sl_price = meta.get("sl_price")
            tp_price = meta.get("tp_price")
            moved_sl = bool(meta.get("moved_sl_to_entry", False))

            # sanity
            if entry_price is None or sl_price is None:
                return None

            entry_price = self._to_dec(entry_price)
            sl_price = self._to_dec(sl_price)
            tp_price = self._to_dec(tp_price) if tp_price is not None else None

            if entry_price is None or sl_price is None:
                return None

            # 1) Move SL to entry at RR=0.5
            if (not moved_sl) and high is not None:
                move_price = self._compute_price_at_rr(entry_price, sl_price, self.move_sl_rr)
                if move_price is not None and high >= move_price:
                    # mark moved
                    meta["moved_sl_to_entry"] = True
                    meta["sl_price"] = entry_price  # update stored SL in meta
                    # Emit a SELL event with special reason to tell Portfolio to UPDATE SL (not close)
                    return SignalEvent(
                        symbol=symbol,
                        signal_type="SELL",
                        price=entry_price,  # new SL price (entry)
                        timestamp=ts,
                        reason=f"MOVE_SL_TO_ENTRY (high={high} >= {move_price} = +{self.move_sl_rr}R)",
                    )

            # 2) TP 1:1 hit => close all
            if tp_price is not None and high is not None and high >= tp_price:
                self.context.close_trade(symbol)
                self.context.transition(key, SCANNING, reason="TP 1:1 hit", now_ts=ts)
                return SignalEvent(
                    symbol=symbol,
                    signal_type="SELL",
                    price=tp_price,  # assume filled at TP
                    timestamp=ts,
                    reason=f"TP 1:1 HIT (high={high} >= tp={tp_price})",
                )

            return None

        # -------------------------
        # Entry state machine
        # -------------------------
        state = self.context.get_state(key)

        if state.phase == SCANNING:
            if not self._detect_reclaim(df_ind):
                return None

            if not self._pullback_filter(df_ind):
                return None

            self.context.transition(key, CONFIRMING, reason="Reclaim EMA21 + pullback ok", now_ts=ts)
            return None

        if state.phase == CONFIRMING:
            if rsi_ema9 is None or rsi_wma45 is None:
                return None

            spread = float(rsi_ema9) - float(rsi_wma45)
            if spread < self.rsi_spread_min:
                self.context.transition(key, SCANNING, reason="Spread too small", now_ts=ts)
                return None

            # SL computed
            sl_price = self._compute_sl(df_ind)
            if sl_price is None:
                # fallback: lowest wick
                self.sl_mode = "lowest_wick"
                sl_price = self._compute_sl(df_ind)

            if sl_price is None:
                self.context.transition(key, SCANNING, reason="No SL computed", now_ts=ts)
                return None

            # Entry logic: Try EMA21 first, but ensure it's above SL
            entry_price = ema21
            if entry_price <= sl_price:
                entry_price = close



            tp_price = self._compute_tp_1to1(entry_price, sl_price)
            if tp_price is None:
                self.context.transition(key, SCANNING, reason="Invalid TP risk", now_ts=ts)
                return None

            if self.use_active_trades:
                self.context.open_trade(
                    symbol=symbol,
                    timeframe=self.timeframe,
                    side="LONG",
                    entry_price=float(entry_price),
                    meta={
                        "entry_price": entry_price,
                        "sl_price": sl_price,
                        "tp_price": tp_price,
                        "rsi_spread": spread,
                        "sl_mode": self.sl_mode,
                        "moved_sl_to_entry": False,
                        "move_sl_rr": self.move_sl_rr,
                    },
                    now_ts=ts,
                )

            # reset state after emitting BUY
            self.context.transition(key, SCANNING, reason="BUY emitted", now_ts=ts)

            return SignalEvent(
                symbol=symbol,
                signal_type="BUY",
                price=entry_price,  # BUY at EMA21
                timestamp=ts,
                reason=f"NO-RETEST BUY (spread={spread:.2f} >= {self.rsi_spread_min})",
                tp1_price=tp_price,  # reuse tp1_price as TP 1:1
                tp2_price=None,
                tp3_price=None,
                sl_price=sl_price,
                signal_class=2,
            )

        self.context.transition(key, SCANNING, reason="Unknown state reset", now_ts=ts)
        return None

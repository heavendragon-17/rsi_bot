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
    + Move SL to 0.2R when price reaches 0.5R
- TP: Partial exits at 1R (50%) and 2R (50% remaining)

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
        "nr_lookback": 30,              # Candles to check for pullback
        "nr_max_above_ema21": 1,        # Max candles above EMA21 in lookback (0 = strict)
        "nr_min_entry_dist_pct": 0.0005, # Min distance close > EMA21 (0.05%)
        "nr_rsi_spread_min": 1.5,       # Min RSI_EMA9 - RSI_WMA45 spread
        
        # SL settings
        "nr_sl_mode": "lowest_wick",   # "rsi_ema9" or "lowest_wick" or "lowest_close"
        "sl_buffer_pct": 0.3,           # No buffer for tight SL
        "sl_check_mode": "close",       # "close" or "wick" - how to check SL hit
        
        # TP settings - Partial exits
        "nr_tp1_rr": 1.0,            # First TP at 1R (take 50%)
        "nr_tp2_rr": 2.0,            # Second TP at 2R (take remaining 50%)
        "nr_tp1_percent": 0.5,       # Take 50% at TP1
        "nr_tp2_percent": 0.5,       # Take 50% at TP2 (of remaining)
        
        # Trade management - Trailing SL
        "nr_move_sl_trigger_rr": 0.5,    # When price hits 0.5R
        "nr_move_sl_to_rr": 0.2,         # Move SL to 0.2R
        
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
        self.min_entry_dist_pct = float(cfg.get("nr_min_entry_dist_pct", 0.0005))
        self.rsi_spread_min = float(cfg.get("nr_rsi_spread_min", 1.5))

        # SL behavior
        self.sl_mode = str(cfg.get("nr_sl_mode", "rsi_ema9")).lower()
        self.sl_buffer_pct = float(cfg.get("sl_buffer_pct", 0.0))
        self.sl_check_mode = str(cfg.get("sl_check_mode", "close")).lower()

        # TP behavior - Partial exits
        self.tp1_rr = Decimal(str(cfg.get("nr_tp1_rr", 1.0)))  # 1R
        self.tp2_rr = Decimal(str(cfg.get("nr_tp2_rr", 2.0)))  # 2R
        self.tp1_percent = Decimal(str(cfg.get("nr_tp1_percent", 0.5)))  # 50%
        self.tp2_percent = Decimal(str(cfg.get("nr_tp2_percent", 0.5)))  # 50%

        # Trailing SL: when price hits 0.5R, move SL to 0.2R
        self.move_sl_trigger_rr = Decimal(str(cfg.get("nr_move_sl_trigger_rr", 0.5)))
        self.move_sl_to_rr = Decimal(str(cfg.get("nr_move_sl_to_rr", 0.2)))
        
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

    def _check_stop_loss_hit(self, low: Optional[Decimal], close: Optional[Decimal], 
                            sl_price: Decimal) -> tuple[bool, Optional[Decimal]]:
        """
        Check if stop loss was hit.
        
        Args:
            low: Current candle's low price
            close: Current candle's close price
            sl_price: Stop loss price level
            
        Returns:
            Tuple of (hit: bool, exit_price: Optional[Decimal])
        """
        if self.sl_check_mode == "wick":
            # Check if low touched or breached SL
            if low is not None and low <= sl_price:
                return True, sl_price
        else:  # "close" mode (default, safer)
            # Check if close is below SL
            if close is not None and close <= sl_price:
                # Exit at close price if below SL, or SL price if close is way below
                exit_price = max(close, sl_price * Decimal("0.95"))  # Allow 5% slippage max
                return True, exit_price
        
        return False, None

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
        low = self._to_dec(last.get("low"))
        ema21 = self._to_dec(last.get("ema21"))

        if close is None or ema21 is None:
            return None

        # RSI values
        rsi_ema9 = last.get("rsi_ema9")
        rsi_wma45 = last.get("rsi_wma45")

        # -------------------------
        # EXIT / MANAGEMENT inside strategy:
        #  0. Stop Loss check (FIRST priority)
        #  1. Move SL to 0.2R when price hits 0.5R
        #  2. TP1 at 1R - close 50%
        #  3. TP2 at 2R - close remaining 50%
        # -------------------------
        if self.use_active_trades and self.context.has_active_trade(symbol):
            trade = self.context.get_trade(symbol)
            meta = trade.meta if trade and trade.meta else {}

            entry_price = meta.get("entry_price")
            original_sl = meta.get("original_sl")  # Store original SL
            sl_price = meta.get("sl_price")
            tp1_price = meta.get("tp1_price")
            tp2_price = meta.get("tp2_price")
            
            # Track partial exits
            tp1_taken = bool(meta.get("tp1_taken", False))
            tp2_taken = bool(meta.get("tp2_taken", False))
            sl_moved = bool(meta.get("sl_moved_to_02r", False))

            # sanity
            if entry_price is None or sl_price is None:
                return None

            entry_price = self._to_dec(entry_price)
            sl_price = self._to_dec(sl_price)
            original_sl = self._to_dec(original_sl) if original_sl else sl_price
            tp1_price = self._to_dec(tp1_price) if tp1_price is not None else None
            tp2_price = self._to_dec(tp2_price) if tp2_price is not None else None

            if entry_price is None or sl_price is None:
                return None

            # 0) STOP LOSS CHECK (highest priority)
            sl_hit, exit_price = self._check_stop_loss_hit(low, close, sl_price)
            if sl_hit:
                self.context.close_trade(symbol)
                self.context.transition(key, SCANNING, reason="Stop Loss Hit", now_ts=ts)
                
                check_method = "wick" if self.sl_check_mode == "wick" else "close"
                return SignalEvent(
                    symbol=symbol,
                    signal_type="SELL",
                    price=exit_price if exit_price else sl_price,
                    timestamp=ts,
                    reason=f"STOP LOSS HIT ({check_method}={low if self.sl_check_mode == 'wick' else close} <= SL={sl_price})",
                )

            # 1) Move SL to 0.2R when price hits 0.5R
            if (not sl_moved) and high is not None:
                trigger_price = self._compute_price_at_rr(entry_price, original_sl, self.move_sl_trigger_rr)
                if trigger_price is not None and high >= trigger_price:
                    new_sl = self._compute_price_at_rr(entry_price, original_sl, self.move_sl_to_rr)
                    if new_sl is not None:
                        meta["sl_moved_to_02r"] = True
                        meta["sl_price"] = new_sl
                        # Update trade meta
                        if trade:
                            trade.meta = meta
                        return SignalEvent(
                            symbol=symbol,
                            signal_type="SELL",
                            price=new_sl,
                            timestamp=ts,
                            reason=f"MOVE_SL_TO_0.2R (high={high} >= {trigger_price} = 0.5R, new_sl={new_sl})",
                        )

            # 2) TP1 at 1R - close 50%
            if (not tp1_taken) and tp1_price is not None and high is not None and high >= tp1_price:
                meta["tp1_taken"] = True
                # Update trade meta
                if trade:
                    trade.meta = meta
                return SignalEvent(
                    symbol=symbol,
                    signal_type="SELL",
                    price=tp1_price,
                    timestamp=ts,
                    reason=f"TP1 HIT at 1R (high={high} >= tp1={tp1_price}) - CLOSE 50%",
                    # quantity_pct=float(self.tp1_percent),  # Close 50%
                )

            # 3) TP2 at 2R - close remaining 50%
            if tp1_taken and (not tp2_taken) and tp2_price is not None and high is not None and high >= tp2_price:
                self.context.close_trade(symbol)
                self.context.transition(key, SCANNING, reason="TP2 hit - all closed", now_ts=ts)
                return SignalEvent(
                    symbol=symbol,
                    signal_type="SELL",
                    price=tp2_price,
                    timestamp=ts,
                    reason=f"TP2 HIT at 2R (high={high} >= tp2={tp2_price}) - CLOSE REMAINING 50%",
                    # quantity_pct=float(self.tp2_percent),  # Close remaining 50%
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

            # Noise filter: close must be > EMA21 by min_dist_pct
            if ema21 and ema21 > 0:
                dist_pct = float((close - ema21) / ema21)
                if dist_pct < self.min_entry_dist_pct:
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

            # Calculate TP levels
            tp1_price = self._compute_price_at_rr(entry_price, sl_price, self.tp1_rr)
            tp2_price = self._compute_price_at_rr(entry_price, sl_price, self.tp2_rr)
            
            if tp1_price is None or tp2_price is None:
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
                        "original_sl": sl_price,  # Store original SL for calculations
                        "sl_price": sl_price,
                        "tp1_price": tp1_price,
                        "tp2_price": tp2_price,
                        "rsi_spread": spread,
                        "sl_mode": self.sl_mode,
                        "tp1_taken": False,
                        "tp2_taken": False,
                        "sl_moved_to_02r": False,
                    },
                    now_ts=ts,
                )

            # reset state after emitting BUY
            self.context.transition(key, SCANNING, reason="BUY emitted", now_ts=ts)

            return SignalEvent(
                symbol=symbol,
                signal_type="BUY",
                price=entry_price,
                timestamp=ts,
                reason=f"NO-RETEST BUY (spread={spread:.2f} >= {self.rsi_spread_min}, TP1={tp1_price}, TP2={tp2_price})",
                tp1_price=tp1_price,
                tp2_price=tp2_price,
                tp3_price=None,
                sl_price=sl_price,
                signal_class=2,
            )

        self.context.transition(key, SCANNING, reason="Unknown state reset", now_ts=ts)
        return None
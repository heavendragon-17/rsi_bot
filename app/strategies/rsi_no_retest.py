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
        "sl_buffer_pct": 0.0,            # No buffer (original behavior)
        "disaster_sl_multiplier": 3.0,   # Disaster SL = 2x distance from entry
        "candle_close_slippage_pct": 0.001,  # 0.1% slippage for candle-close exits
        
        # TP settings
        "nr_tp1_rr": 1.0,            # TP1: 1R (Close 50%)
        "nr_tp2_rr": 2.0,            # TP2: 2R (Close 25%)
        "nr_tp3_rr": 3.0,            # TP3: 3R (Close 25%)
        "tp1_close_pct": 0.50,
        "tp2_close_pct": 0.25,
        "tp3_close_pct": 0.25,

        # SL management
        "nr_move_sl_rr": 0.5,        # Trigger: move SL when high reaches 0.5R (halfway to TP1)
        "nr_lock_profit_rr": 0.2,    # New SL level: 0.2R above entry (lock 20% of profit)

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
        
        # Disaster SL multiplier (2x means disaster SL is 2x further than soft SL)
        self.disaster_sl_multiplier = float(cfg.get("disaster_sl_multiplier", 2.0))
        
        # Slippage for candle close exits
        self.candle_close_slippage_pct = float(cfg.get("candle_close_slippage_pct", 0.001))

        # TP behavior
        self.tp1_rr = Decimal(str(cfg.get("nr_tp1_rr", 1.0)))
        self.tp2_rr = Decimal(str(cfg.get("nr_tp2_rr", 2.0)))
        self.tp3_rr = Decimal(str(cfg.get("nr_tp3_rr", 3.0)))

        # NEW: Move SL trigger and lock level
        self.move_sl_rr = Decimal(str(cfg.get("nr_move_sl_rr", 0.5)))       # Trigger at 0.5R
        self.lock_profit_rr = Decimal(str(cfg.get("nr_lock_profit_rr", 0.2))) # Lock 20% profit
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
            sl_price = meta.get("sl_price")  # This is now Soft SL (for candle close check)
            soft_sl = meta.get("soft_sl_price")  # Explicit soft SL if available
            tp_price = meta.get("tp_price")
            moved_sl = bool(meta.get("moved_sl_to_entry", False))
            pending_candle_sl = bool(meta.get("pending_candle_sl", False))

            # sanity
            if entry_price is None:
                return None

            entry_price = self._to_dec(entry_price)
            sl_price = self._to_dec(sl_price) if sl_price is not None else None
            soft_sl = self._to_dec(soft_sl) if soft_sl is not None else sl_price  # Fallback to sl_price
            tp_price = self._to_dec(tp_price) if tp_price is not None else None
            open_price = self._to_dec(last.get("open"))

            if entry_price is None:
                return None

            # -------------------------------------------------
            # STEP 0: Handle pending Close by Candle SL from previous candle
            # Exit at THIS candle's OPEN price (simulates "next candle open")
            # -------------------------------------------------
            if pending_candle_sl and open_price is not None:
                self.context.close_trade(symbol)
                self.context.transition(key, SCANNING, reason="Close by Candle SL executed at next open", now_ts=ts)
                return SignalEvent(
                    symbol=symbol,
                    signal_type="SELL",
                    price=open_price,  # Exit at THIS candle's open (= previous candle's "next open")
                    timestamp=ts,
                    reason="CLOSE_BY_CANDLE_SL",
                )

            # -------------------------------------------------
            # STEP 1: TP Logic (TP1 -> TP2 -> TP3)
            # -------------------------------------------------
            # Check TP hits
            tp1_hit = meta.get("tp1_hit", False)
            tp2_hit = meta.get("tp2_hit", False)
            tp3_hit = meta.get("tp3_hit", False)
            
            tp1_price = self._to_dec(meta.get("tp1_price"))
            tp2_price = self._to_dec(meta.get("tp2_price"))
            tp3_price = self._to_dec(meta.get("tp3_price"))
            
            # Target SL (0.2R) - use ORIGINAL soft SL, not dynamic sl_price which may be updated
            original_soft_sl = self._to_dec(meta.get("original_soft_sl")) or sl_price
            lock_profit_price = None
            if original_soft_sl and entry_price:
                 lock_profit_price = self._compute_price_at_rr(entry_price, original_soft_sl, self.lock_profit_rr)

            # TP3: Close remaining
            if (not tp3_hit) and tp3_price and high is not None and high >= tp3_price:
                self.context.close_trade(symbol)
                self.context.transition(key, SCANNING, reason="TP3 hit -> full exit", now_ts=ts)
                return SignalEvent(
                    symbol=symbol,
                    signal_type="SELL",
                    price=tp3_price,
                    timestamp=ts,
                    reason=f"TP3 (>{self.tp3_rr}R)",
                )
            
            # TP2: Partial Close
            if (not tp2_hit) and tp2_price and high is not None and high >= tp2_price:
                meta["tp2_hit"] = True
                # Ensure we maintain the current SL price (e.g. 0.2R) but update amount in Portfolio
                current_sl = meta.get("sl_price")
                return SignalEvent(
                    symbol=symbol,
                    signal_type="SELL",
                    price=tp2_price,
                    timestamp=ts,
                    reason=f"TP2 (>{self.tp2_rr}R)",
                    sl_price=current_sl,
                )

            # TP1: Partial Close + Move SL to 0.2R
            if (not tp1_hit) and tp1_price and high is not None and high >= tp1_price:
                meta["tp1_hit"] = True
                # Mark SL as moved in meta so we don't try to move it again unnecessarily
                meta["moved_sl_to_entry"] = True 
                if lock_profit_price:
                    meta["sl_price"] = lock_profit_price
                    meta["soft_sl_price"] = lock_profit_price
                
                return SignalEvent(
                    symbol=symbol,
                    signal_type="SELL",
                    price=tp1_price,
                    timestamp=ts,
                    reason=f"TP1 (>{self.tp1_rr}R)",
                    sl_price=lock_profit_price,  # Tell Portfolio to move SL here
                )

            # -------------------------------------------------
            # STEP 2: Move SL to lock profit when price reaches 0.5R
            # Only if TP1 hasn't hit yet (TP1 hit already moves SL to 0.2R)
            # -------------------------------------------------
            if (not moved_sl) and (not tp1_hit) and high is not None and sl_price is not None:
                move_trigger = self._compute_price_at_rr(entry_price, sl_price, self.move_sl_rr)
                if move_trigger is not None and high >= move_trigger:
                     # Calculate new SL at 0.2R
                    new_sl = lock_profit_price
                    if new_sl is not None:
                        # mark moved
                        meta["moved_sl_to_entry"] = True
                        meta["sl_price"] = new_sl  # update stored SL in meta
                        meta["soft_sl_price"] = new_sl  # also update soft SL
                        # Emit a SELL event with special reason to tell Portfolio to UPDATE SL (not close)
                        return SignalEvent(
                            symbol=symbol,
                            signal_type="SELL",
                            price=new_sl,  # new SL price
                            timestamp=ts,
                            reason=f"MOVE_SL_LOCK_PROFIT (high={high} >= {move_trigger} = +{self.move_sl_rr}R, new_sl={new_sl} = +{self.lock_profit_rr}R)",
                        )

            # -------------------------------------------------
            # STEP 3: Close by Candle SL (LAST - only if TP not hit)
            # Set flag to exit at NEXT candle's open
            # -------------------------------------------------
            if soft_sl is not None and close is not None:
                if close <= soft_sl:
                    # Mark for exit at next candle's open
                    meta["pending_candle_sl"] = True
                    # Don't close yet - wait for next candle
                    return None

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
            # Entry logic: Market order at next open (simulated by current close)
            entry_price = close

            tp1_price = self._compute_price_at_rr(entry_price, sl_price, self.tp1_rr)
            tp2_price = self._compute_price_at_rr(entry_price, sl_price, self.tp2_rr)
            tp3_price = self._compute_price_at_rr(entry_price, sl_price, self.tp3_rr)
            
            if tp1_price is None:
                self.context.transition(key, SCANNING, reason="Invalid TP risk", now_ts=ts)
                return None

            # -------------------------------------------------
            # Dual SL System:
            # 1. Soft SL: sl_price with buffer (for candle-close exit logic)
            # 2. Disaster SL: multiplier x distance from entry (hard limit order)
            # -------------------------------------------------
            soft_sl_price = sl_price  # Already has buffer applied from _compute_sl
            disaster_sl_price = None
            
            if soft_sl_price is not None:
                soft_sl_distance = entry_price - soft_sl_price
                disaster_sl_price = entry_price - (soft_sl_distance * Decimal(str(self.disaster_sl_multiplier)))

            if self.use_active_trades:
                self.context.open_trade(
                    symbol=symbol,
                    timeframe=self.timeframe,
                    side="LONG",
                    entry_price=float(entry_price),
                    meta={
                        "entry_price": entry_price,
                        "sl_price": soft_sl_price,  # Used for candle close check
                        "soft_sl_price": soft_sl_price,  # Explicit soft SL
                        "original_soft_sl": soft_sl_price,  # NEVER MODIFIED - used for lock_profit calc
                        "disaster_sl_price": disaster_sl_price,  # Reference only
                        "tp1_price": tp1_price,
                        "tp2_price": tp2_price,
                        "tp3_price": tp3_price,
                        "tp1_hit": False,
                        "tp2_hit": False,
                        "tp3_hit": False,
                        "rsi_spread": spread,
                        "sl_mode": self.sl_mode,
                        "moved_sl_to_entry": False,
                        "move_sl_rr": self.move_sl_rr,
                        "lock_profit_rr": self.lock_profit_rr,
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
                tp1_price=tp1_price,
                tp2_price=tp2_price,
                tp3_price=tp3_price,
                sl_price=disaster_sl_price,  # Hard limit order on exchange
                soft_sl_price=soft_sl_price,  # For portfolio reference
                signal_class=2,
            )

        self.context.transition(key, SCANNING, reason="Unknown state reset", now_ts=ts)
        return None

"""
Layer 2: Core Logic - RSI WMA Retest Strategy (CORRECTED)
==========================================================
LONG ONLY strategy using TWO CHARTS:
- Price Chart: EMA21, EMA200, R40/R60/R70/R80 price levels
- RSI Chart: RSI(21), EMA9, WMA45
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional, Any
from datetime import datetime

from app.strategies.base import BaseStrategy
from app.utils.indicators import Indicators, MODE_BULLISH, MODE_NEUTRAL
from app.core.events import SignalEvent
from app.core.context import StrategyContext, SCANNING, RETESTING, CONFIRMING


def _normalize_ts(ts: Any) -> Any:
    """
    Normalize timestamp without forcing int().
    Keeps datetime/pandas.Timestamp as datetime-like (best for backtests).
    """
    if ts is None:
        return None

    # pandas.Timestamp -> datetime
    try:
        import pandas as pd
        if isinstance(ts, pd.Timestamp):
            return ts.to_pydatetime()
    except Exception:
        pass

    if isinstance(ts, datetime):
        return ts

    if isinstance(ts, (int, float)):
        return ts

    try:
        return int(ts)
    except Exception:
        return ts


class RsiWmaRetestStrategy(BaseStrategy):
    """
    RSI WMA Retest Strategy - LONG ONLY

    Entry (state machine):
      1) SCANNING:
         - RSI > EMA9(RSI)
         - RSI > WMA45(RSI)
         - EMA9(RSI) > WMA45(RSI)
         - price > EMA200(price)
      2) RETESTING:
         - RSI comes back near WMA45 within wma_retest_distance
         - price must NOT close below stored R40 price
      3) CONFIRMING:
         - price crosses UP through EMA21 (prev_close <= prev_ema21 and close > ema21)
         - RSI bounced above WMA45
         - WMA45 filter 30..60 -> class 1/2

    Exit:
      - STOPLOSS (price): if low <= sl_price (intrabar) else close <= sl_price
      - RSI overbought exit: rsi > rsi_sell

    Anti-chop:
      - After STOPLOSS, lock entries for sl_lock_candles (default 12 candles on 5m = 60 minutes).
    """

    def __init__(self, config: dict):
        super().__init__(config)

        # Ensure self.context exists
        if hasattr(self, "ctx") and not hasattr(self, "context"):
            self.context = self.ctx  # type: ignore[attr-defined]
        if not hasattr(self, "context"):
            self.context = StrategyContext()

        strategy_cfg = config.get("strategy", {})
        bot_cfg = config.get("bot", {})

        self.timeframe = bot_cfg.get("timeframe", "5m")

        self.indicators = Indicators(
            rsi_length=strategy_cfg.get("rsi_period", 14),
            rsi_ema_length=strategy_cfg.get("rsi_ema_length", 9),
            rsi_wma_length=strategy_cfg.get("rsi_wma_length", 45),
            price_ema_fast=strategy_cfg.get("price_ema_fast", 21),
            price_ema_slow=strategy_cfg.get("price_ema_slow", 200),
        )

        self.wma_retest_distance = float(strategy_cfg.get("wma_retest_distance", 3.0))

        self.wma45_class1_min = float(strategy_cfg.get("wma45_min", 30.0))
        self.wma45_class1_max = float(strategy_cfg.get("wma45_max", 50.0))
        self.wma45_class2_max = float(strategy_cfg.get("wma45_class2_max", 60.0))

        self.tp1_rsi = float(strategy_cfg.get("tp1_rsi", 60.0))
        self.tp2_rsi = float(strategy_cfg.get("tp2_rsi", 70.0))
        self.tp3_rsi = float(strategy_cfg.get("tp3_rsi", 80.0))
        self.sl_buffer_pct = float(strategy_cfg.get("sl_buffer_pct", 0.003))

        # Time cooldown (still useful, but not your main anti-chop tool)
        self.cooldown_sec = int(strategy_cfg.get("cooldown_sec", 300))

        # Lock entries after SL for N candles (5m candles)
        self.sl_lock_candles = int(strategy_cfg.get("sl_lock_candles", 12))

        self.rsi_sell = float(strategy_cfg.get("rsi_sell", 80.0))
        self.use_active_trades = bool(strategy_cfg.get("use_active_trades", True))

        self._r40_price_at_retest: dict[str, Optional[Decimal]] = {}

    def analyze(self, symbol: str, df) -> Optional[SignalEvent]:
        if df is None or len(df) < 220:
            return None

        if "closed" in df.columns and not bool(df.iloc[-1]["closed"]):
            return None

        key = f"{symbol}:{self.timeframe}"

        df_ind = self.indicators.compute(df, symbol=symbol, timeframe=self.timeframe)
        last = Indicators.last(df_ind)
        if not last:
            return None

        rsi = last.get("rsi")
        if rsi is None:
            return None

        close = last.get("close")
        ema21 = last.get("ema21")
        ema200 = last.get("ema200")
        rsi_ema9 = last.get("rsi_ema9")
        rsi_wma45 = last.get("rsi_wma45")
        low = last.get("low")

        prev = df_ind.iloc[-2] if len(df_ind) > 1 else None
        prev_close = prev.get("close") if prev is not None else None
        prev_ema21 = prev.get("ema21") if prev is not None else None

        # Candle timestamp: always prefer df index
        ts = None
        try:
            ts = df_ind.index[-1]
        except Exception:
            ts = last.get("ts")
        ts = _normalize_ts(ts)

        close_dec = Decimal(str(close)) if close is not None else None
        low_dec = Decimal(str(low)) if low is not None else None

        # ==================================================
        # EXIT LOGIC (active trade) - runs even if waiting
        # ==================================================
        if self.use_active_trades and self.context.has_active_trade(symbol):
            trade = self.context.get_trade(symbol)
            meta = trade.meta if trade is not None else {}
            sl_price = meta.get("sl_price")

            # STOPLOSS hit
            if sl_price is not None:
                if low_dec is not None and low_dec <= sl_price:
                    # Close trade + reset state + SL lock
                    self.context.close_trade(symbol)
                    self.context.clear_waiting(key, now_ts=ts)
                    self.context.set_sl_lock(key, timeframe=self.timeframe, candles=self.sl_lock_candles, now_ts=ts)
                    self.context.transition(key, SCANNING, reason="Stoploss hit", now_ts=ts)
                    self._r40_price_at_retest.pop(key, None)

                    return SignalEvent(
                        symbol=symbol,
                        signal_type="SELL",
                        price=close_dec if close_dec is not None else Decimal("0"),
                        timestamp=ts,
                        reason=f"STOPLOSS HIT (low={low_dec} <= SL={sl_price})",
                    )

                if low_dec is None and close_dec is not None and close_dec <= sl_price:
                    self.context.close_trade(symbol)
                    self.context.clear_waiting(key, now_ts=ts)
                    self.context.set_sl_lock(key, timeframe=self.timeframe, candles=self.sl_lock_candles, now_ts=ts)
                    self.context.transition(key, SCANNING, reason="Stoploss hit (close)", now_ts=ts)
                    self._r40_price_at_retest.pop(key, None)

                    return SignalEvent(
                        symbol=symbol,
                        signal_type="SELL",
                        price=close_dec,
                        timestamp=ts,
                        reason=f"STOPLOSS HIT (close={close_dec} <= SL={sl_price})",
                    )

            # RSI overbought exit (TP/exit)
            if rsi > self.rsi_sell:
                self.context.close_trade(symbol)
                self.context.clear_waiting(key, now_ts=ts)
                self.context.transition(key, SCANNING, reason="RSI overbought exit", now_ts=ts)
                self._r40_price_at_retest.pop(key, None)

                return SignalEvent(
                    symbol=symbol,
                    signal_type="SELL",
                    price=close_dec if close_dec is not None else Decimal("0"),
                    timestamp=ts,
                    reason=f"RSI OVERBOUGHT ({rsi:.2f} > {self.rsi_sell})",
                )

            return None

        # ==================================================
        # ENTRY BLOCKERS
        # ==================================================
        # 1) SL lock (anti-chop re-entry)
        if self.context.is_sl_locked(key, now_ts=ts):
            return None

        # 2) Waiting (cooldown between signals)
        if self.context.is_waiting(key, now_ts=ts):
            return None

        # 3) Active trade lock
        if self.use_active_trades and self.context.has_active_trade(symbol):
            return None

        # ==================================================
        # ENTRY LOGIC - State Machine
        # ==================================================
        state = self.context.get_state(key)

        # STATE 1: SCANNING
        if state.phase == SCANNING:
            if (
                rsi_ema9 is not None
                and rsi_wma45 is not None
                and ema200 is not None
                and close is not None
                and rsi > rsi_ema9
                and rsi > rsi_wma45
                and rsi_ema9 > rsi_wma45
                and close > ema200
            ):
                r40_price = self.indicators.calculate_price_at_rsi(df_ind, 40)
                self._r40_price_at_retest[key] = r40_price
                self.context.transition(key, RETESTING, reason="Setup valid - watching for retest", now_ts=ts)
            return None

        # STATE 2: RETESTING
        if state.phase == RETESTING:
            if rsi_wma45 is None:
                return None

            r40_price = self._r40_price_at_retest.get(key)
            if r40_price is not None and close_dec is not None:
                if close_dec < r40_price:
                    self.context.transition(key, SCANNING, reason="Price closed below R40 level", now_ts=ts)
                    return None

            distance = abs(rsi - rsi_wma45)
            if distance <= self.wma_retest_distance:
                state.retest_touched_ts = ts
                self.context.transition(key, CONFIRMING, reason=f"RSI retested WMA45 (dist={distance:.1f})", now_ts=ts)
            return None

        # STATE 3: CONFIRMING
        if state.phase == CONFIRMING:
            if close is None or ema21 is None or rsi_wma45 is None:
                return None
            if prev_close is None or prev_ema21 is None:
                return None

            crossed_up = (prev_close <= prev_ema21) and (close > ema21)
            rsi_bounced = rsi > rsi_wma45

            if crossed_up and rsi_bounced:
                if not self.context.can_alert(key, self.cooldown_sec, now_ts=ts):
                    return None
                self.context.mark_alerted(key, now_ts=ts)

                # Classify by WMA45
                if self.wma45_class1_min <= rsi_wma45 <= self.wma45_class1_max:
                    signal_class = 1
                elif rsi_wma45 <= self.wma45_class2_max:
                    signal_class = 2
                else:
                    self.context.transition(key, SCANNING, reason="WMA45 > 60, skipping", now_ts=ts)
                    return None

                tp1_price = self.indicators.calculate_price_at_rsi(df_ind, self.tp1_rsi)
                tp2_price = self.indicators.calculate_price_at_rsi(df_ind, self.tp2_rsi)
                tp3_price = self.indicators.calculate_price_at_rsi(df_ind, self.tp3_rsi)
                sl_price_raw = self.indicators.calculate_price_at_rsi(df_ind, 40)

                sl_price = None
                if sl_price_raw is not None:
                    sl_price = sl_price_raw * Decimal(str(1 - self.sl_buffer_pct))

                if self.use_active_trades:
                    self.context.open_trade(
                        symbol=symbol,
                        timeframe=self.timeframe,
                        side="LONG",
                        entry_price=close,
                        meta={
                            "tp1_price": tp1_price,
                            "tp2_price": tp2_price,
                            "tp3_price": tp3_price,
                            "sl_price": sl_price,
                            "signal_class": signal_class,
                        },
                        now_ts=ts,
                    )

                self.context.set_waiting(
                    key,
                    seconds=self.cooldown_sec,
                    reason="BUY signal triggered - waiting",
                    now_ts=ts,
                )

                return SignalEvent(
                    symbol=symbol,
                    signal_type="BUY",
                    price=Decimal(str(close)),
                    timestamp=ts,
                    reason=f"Retest confirmed + EMA21 crossup (WMA45={rsi_wma45:.1f}, Class {signal_class})",
                    tp1_price=tp1_price,
                    tp2_price=tp2_price,
                    tp3_price=tp3_price,
                    sl_price=sl_price,
                    signal_class=signal_class,
                )

            # Reset if RSI drops too far below WMA45 while confirming
            if rsi < rsi_wma45 - 5:
                self.context.transition(key, SCANNING, reason="RSI dropped too far below WMA45", now_ts=ts)

            return None

        # Safety reset
        self.context.transition(key, SCANNING, reason="Unknown state reset", now_ts=ts)
        return None

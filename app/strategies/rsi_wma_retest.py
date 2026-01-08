from __future__ import annotations

from app.strategies.base import BaseStrategy
from app.utils.indicators import Indicators
from app.core.events import SignalEvent
from app.core.context import SCANNING, RETESTING, CONFIRMING


class RsiWmaRetestStrategy(BaseStrategy):
    """
    Strategy combines:
      1) 3-step RSI retest state machine (main entry logic)
      2) Simple RSI oversold/overbought signals (optional fast entry + exit)

    State machine (BUY):
      - SCANNING:   RSI > EMA9(RSI) and RSI > WMA45(RSI) and price > EMA200(price)
      - RETESTING:  RSI retests WMA45(RSI) but stays above RSI floor (e.g. RSI40)
      - CONFIRMING: candle close > EMA21(price) -> BUY signal

    Simple rules:
      - BUY  when RSI < rsi_buy (optional fast entry, trend-filtered)
      - SELL when RSI > rsi_sell (exit, only when an active trade exists)

    Notes:
      - Requires StrategyContext in BaseStrategy as: self.context
      - Uses WAITING + cooldown to prevent spam
      - Uses active_trades to lock symbol while a trade is active (optional)
    """

    def __init__(self, config):
        super().__init__(config)

        bot_cfg = self.config.get("bot", {})
        strategy_cfg = self.config.get("strategy", {})

        # Timeframe used for keying state machine (symbol:timeframe)
        self.timeframe = bot_cfg.get("timeframe", "1m")

        # Indicator parameters
        self.indicators = Indicators(
            rsi_length=strategy_cfg.get("rsi_period", 14),
            rsi_ema_length=strategy_cfg.get("rsi_ema_length", 9),
            rsi_wma_length=strategy_cfg.get("rsi_wma_length", 45),
            price_ema_fast=strategy_cfg.get("price_ema_fast", 21),
            price_ema_slow=strategy_cfg.get("price_ema_slow", 200),
        )

        # State machine thresholds
        self.rsi_floor = float(strategy_cfg.get("rsi_floor", 40.0))
        self.retest_band = float(strategy_cfg.get("retest_band", 1.5))
        self.cooldown_sec = int(strategy_cfg.get("cooldown_sec", 300))

        # Simple RSI thresholds (fast entry / exit)
        self.rsi_buy = float(strategy_cfg.get("rsi_buy", 30.0))
        self.rsi_sell = float(strategy_cfg.get("rsi_sell", 80.0))

        # If True, mark BUY as an active trade and require SELL to close it
        self.use_active_trades = bool(strategy_cfg.get("use_active_trades", True))

    def analyze(self, symbol: str, df):
        if df is None or len(df) < 220:
            return None

        # Only evaluate on closed candles (recommended for stable signals)
        if "is_closed" in df.columns and not bool(df.iloc[-1]["is_closed"]):
            return None

        key = f"{symbol}:{self.timeframe}"

        # Compute indicators
        df_ind = self.indicators.compute(df, symbol=symbol, timeframe=self.timeframe)
        last = Indicators.last(df_ind)
        if not last:
            return None

        last_rsi = last.get("rsi")
        if last_rsi is None:
            return None

        close = last.get("close")
        ema21 = last.get("ema21")
        ema200 = last.get("ema200")
        rsi_ema9 = last.get("rsi_ema9")
        rsi_wma45 = last.get("rsi_wma45")
        ts = last.get("ts")

        # Timestamp fallback: prefer indicator candle ts, otherwise df index
        if ts is None:
            try:
                ts = int(df.index[-1])
            except Exception:
                ts = None
        else:
            ts = int(ts)

        # --------------------------------------------------
        # EXIT LOGIC (SELL) - only when an active trade exists
        # This should run even if the symbol is in WAITING.
        # --------------------------------------------------
        if self.use_active_trades and self.context.has_active_trade(symbol):
            if last_rsi > self.rsi_sell:
                self.context.close_trade(symbol)
                self.context.transition(key, SCANNING, reason="RSI overbought SELL")

                return SignalEvent(
                    symbol=symbol,
                    signal_type="SELL",
                    price=close,
                    timestamp=ts,
                    reason=f"RSI OVERBOUGHT ({last_rsi:.2f} > {self.rsi_sell})",
                )

        # --------------------------------------------------
        # Hard stop: do nothing while waiting
        # --------------------------------------------------
        if self.context.is_waiting(key):
            return None

        # If you use active trades, skip any new BUY/alerts while a trade is open
        if self.use_active_trades and self.context.has_active_trade(symbol):
            return None

        # --------------------------------------------------
        # SIMPLE FAST ENTRY (BUY) - optional
        # Only allowed when:
        #   - not waiting
        #   - no active trade
        #   - price trend filter passes (close > EMA200)
        # --------------------------------------------------
        if close is not None and ema200 is not None:
            if last_rsi < self.rsi_buy and close > ema200:
                if not self.context.can_alert(key, self.cooldown_sec):
                    return None

                self.context.mark_alerted(key)

                if self.use_active_trades:
                    self.context.open_trade(
                        symbol=symbol,
                        timeframe=self.timeframe,
                        side="LONG",
                        entry_price=close,
                    )

                self.context.set_waiting(
                    key,
                    seconds=self.cooldown_sec,
                    reason="RSI oversold BUY (fast entry)",
                )

                return SignalEvent(
                    symbol=symbol,
                    signal_type="BUY",
                    price=close,
                    timestamp=ts,
                    reason=f"RSI OVERSOLD ({last_rsi:.2f} < {self.rsi_buy})",
                )

        # --------------------------------------------------
        # STATE MACHINE (main BUY logic)
        # --------------------------------------------------
        state = self.context.get_state(key)

        # Global invalidation: RSI broke below floor -> reset state machine
        if last_rsi < self.rsi_floor:
            self.context.transition(key, SCANNING, reason="RSI broke below floor")
            return None

        # STATE 1: SCANNING
        if state.phase == SCANNING:
            if (
                rsi_ema9 is not None
                and rsi_wma45 is not None
                and ema200 is not None
                and close is not None
                and last_rsi > rsi_ema9
                and last_rsi > rsi_wma45
                and close > ema200
            ):
                self.context.transition(key, RETESTING, reason="Initial setup valid")
            return None

        # STATE 2: RETESTING
        if state.phase == RETESTING:
            if rsi_wma45 is None:
                return None

            # "Retest WMA45 zone" definition:
            # RSI is close to WMA45(RSI) within retest_band points.
            touched = abs(last_rsi - rsi_wma45) <= self.retest_band

            if touched:
                state.retest_touched_ts = ts
                self.context.transition(key, CONFIRMING, reason="RSI retested WMA45")
            return None

        # STATE 3: CONFIRMING
        if state.phase == CONFIRMING:
            if close is None or ema21 is None:
                return None

            # Confirmation: candle close > EMA21(price)
            if close > ema21:
                if not self.context.can_alert(key, self.cooldown_sec):
                    return None

                self.context.mark_alerted(key)

                if self.use_active_trades:
                    self.context.open_trade(
                        symbol=symbol,
                        timeframe=self.timeframe,
                        side="LONG",
                        entry_price=close,
                    )

                self.context.set_waiting(
                    key,
                    seconds=self.cooldown_sec,
                    reason="Retest confirmed BUY -> waiting",
                )

                return SignalEvent(
                    symbol=symbol,
                    signal_type="BUY",
                    price=close,
                    timestamp=ts,
                    reason="RSI retest confirmed + close > EMA21",
                )

            return None

        # Safety reset
        self.context.transition(key, SCANNING, reason="Unknown state reset")
        return None

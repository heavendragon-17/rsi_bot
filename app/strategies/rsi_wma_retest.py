"""
Layer 2: Core Logic - RSI WMA Retest Strategy (CORRECTED)
==========================================================
LONG ONLY strategy using TWO CHARTS:
- Price Chart: EMA21, EMA200, R40/R60/R70/R80 price levels
- RSI Chart: RSI(21), EMA9, WMA45
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from app.strategies.base import BaseStrategy
from app.utils.indicators import Indicators, MODE_BULLISH, MODE_NEUTRAL
from app.core.events import SignalEvent
from app.core.context import StrategyContext, SCANNING, RETESTING, CONFIRMING, WAITING


class RsiWmaRetestStrategy(BaseStrategy):
    """
    RSI WMA Retest Strategy - LONG ONLY
    
    Uses TWO CHARTS:
    - Price Chart: Candles, EMA21, EMA200
    - RSI Chart: RSI, EMA9(RSI), WMA45(RSI)
    
    Entry Conditions:
    1. RSI above EMA9 AND WMA45, with EMA9 > WMA45 (RSI Chart)
    2. RSI retests WMA45 (within 3 units) (RSI Chart)
    3. No candle closed below R40 PRICE level during retest (Price Chart)
    4. Price CROSSES UP through EMA21 (Price Chart)
    5. WMA45 in 30-60 range determines signal class (RSI Chart)
    
    Exit (TP):
    - TP1: RSI >= 60 (partial close, move SL to entry)
    - TP2: RSI >= 70 (close ⅔ or full)
    - TP3: RSI >= 80 (mandatory 100%)
    
    Exit (SL):
    - Limit order at R40 price - 0.3% buffer
    """

    def __init__(self, config: dict):
        super().__init__(config)

        strategy_cfg = config.get("strategy", {})
        bot_cfg = config.get("bot", {})

        self.timeframe = bot_cfg.get("timeframe", "5m")

        # Initialize indicators
        self.indicators = Indicators(
            rsi_length=strategy_cfg.get("rsi_period", 14),
            rsi_ema_length=strategy_cfg.get("rsi_ema_length", 9),
            rsi_wma_length=strategy_cfg.get("rsi_wma_length", 45),
            price_ema_fast=strategy_cfg.get("price_ema_fast", 21),
            price_ema_slow=strategy_cfg.get("price_ema_slow", 200),
        )

        # Entry parameters
        self.wma_retest_distance = float(strategy_cfg.get("wma_retest_distance", 3.0))
        
        # WMA45 range for signal classification
        self.wma45_class1_min = float(strategy_cfg.get("wma45_min", 30.0))
        self.wma45_class1_max = float(strategy_cfg.get("wma45_max", 50.0))
        self.wma45_class2_max = float(strategy_cfg.get("wma45_class2_max", 60.0))

        # TP/SL parameters
        self.tp1_rsi = float(strategy_cfg.get("tp1_rsi", 60.0))
        self.tp2_rsi = float(strategy_cfg.get("tp2_rsi", 70.0))
        self.tp3_rsi = float(strategy_cfg.get("tp3_rsi", 80.0))
        self.sl_buffer_pct = float(strategy_cfg.get("sl_buffer_pct", 0.003))

        # Cooldown
        self.cooldown_sec = int(strategy_cfg.get("cooldown_sec", 300))
        
        # RSI overbought exit
        self.rsi_sell = float(strategy_cfg.get("rsi_sell", 80.0))
        
        # Track active trades
        self.use_active_trades = bool(strategy_cfg.get("use_active_trades", True))
        
        # Store R40 price at retest time for floor check
        self._r40_price_at_retest = {}

    def analyze(self, symbol: str, df) -> Optional[SignalEvent]:
        """
        Main strategy analysis method.
        Returns SignalEvent if entry/exit conditions are met.
        """
        if df is None or len(df) < 220:
            return None

        # Only evaluate on closed candles
        if "closed" in df.columns and not bool(df.iloc[-1]["closed"]):
            return None

        key = f"{symbol}:{self.timeframe}"

        # Compute indicators
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

        # Get previous candle for cross detection
        prev = df_ind.iloc[-2] if len(df_ind) > 1 else None
        prev_close = prev.get("close") if prev is not None else None
        prev_ema21 = prev.get("ema21") if prev is not None else None

        # Get timestamp
        ts = last.get("ts")
        if ts is None:
            try:
                ts = int(df.index[-1])
            except Exception:
                ts = None
        else:
            ts = int(ts)

        # --------------------------------------------------
        # EXIT LOGIC (SELL) - Check for RSI overbought exit
        # --------------------------------------------------
        if self.use_active_trades and self.context.has_active_trade(symbol):
            if rsi > self.rsi_sell:
                self.context.close_trade(symbol)
                self.context.transition(key, SCANNING, reason="RSI overbought exit")

                return SignalEvent(
                    symbol=symbol,
                    signal_type="SELL",
                    price=Decimal(str(close)) if close else Decimal("0"),
                    timestamp=ts,
                    reason=f"RSI OVERBOUGHT ({rsi:.2f} > {self.rsi_sell})",
                )

        # Skip if waiting
        if self.context.is_waiting(key):
            return None

        # Skip if active trade exists
        if self.use_active_trades and self.context.has_active_trade(symbol):
            return None

        # --------------------------------------------------
        # ENTRY LOGIC - State Machine
        # --------------------------------------------------
        state = self.context.get_state(key)

        # --------------------------------------------------
        # STATE 1: SCANNING (RSI Chart)
        # Looking for: RSI > EMA9 > WMA45
        # --------------------------------------------------
        if state.phase == SCANNING:
            if (
                rsi_ema9 is not None
                and rsi_wma45 is not None
                and ema200 is not None
                and close is not None
                and rsi > rsi_ema9                    # RSI above EMA9
                and rsi > rsi_wma45                   # RSI above WMA45
                and rsi_ema9 > rsi_wma45              # EMA9 above WMA45 (NEW!)
                and close > ema200                    # Price above EMA200 (trend filter)
            ):
                # Store R40 price at this point
                r40_price = self.indicators.calculate_price_at_rsi(df_ind, 40)
                self._r40_price_at_retest[key] = r40_price
                
                self.context.transition(key, RETESTING, reason="Setup valid - watching for retest")
            return None

        # --------------------------------------------------
        # STATE 2: RETESTING (RSI Chart + Price Chart)
        # Waiting for RSI to retest WMA45
        # --------------------------------------------------
        if state.phase == RETESTING:
            if rsi_wma45 is None:
                return None

            # Check R40 PRICE floor (not RSI 40!)
            r40_price = self._r40_price_at_retest.get(key)
            if r40_price is not None and close is not None:
                if Decimal(str(close)) < r40_price:
                    # Price closed below R40 - invalidate
                    self.context.transition(key, SCANNING, reason="Price closed below R40 level")
                    return None

            # Check for retest (RSI within distance of WMA45)
            distance = abs(rsi - rsi_wma45)
            if distance <= self.wma_retest_distance:
                state.retest_touched_ts = ts
                self.context.transition(key, CONFIRMING, reason=f"RSI retested WMA45 (dist={distance:.1f})")
            return None

        # --------------------------------------------------
        # STATE 3: CONFIRMING (Price Chart)
        # Waiting for price to CROSS UP through EMA21
        # --------------------------------------------------
        if state.phase == CONFIRMING:
            if close is None or ema21 is None or rsi_wma45 is None:
                return None
            
            if prev_close is None or prev_ema21 is None:
                return None

            # Check price CROSSED UP through EMA21
            # Previous close was at or below EMA21, current close above
            crossed_up = (prev_close <= prev_ema21) and (close > ema21)
            
            # Also check RSI bounced back above WMA45
            rsi_bounced = rsi > rsi_wma45

            if crossed_up and rsi_bounced:
                if not self.context.can_alert(key, self.cooldown_sec):
                    return None

                self.context.mark_alerted(key)

                # Determine signal class based on WMA45 position
                if self.wma45_class1_min <= rsi_wma45 <= self.wma45_class1_max:
                    signal_class = 1  # Full position
                elif rsi_wma45 <= self.wma45_class2_max:
                    signal_class = 2  # 50% position
                else:
                    # WMA45 > 60, skip this signal
                    self.context.transition(key, SCANNING, reason="WMA45 > 60, skipping")
                    return None

                # Calculate TP/SL prices
                tp1_price = self.indicators.calculate_price_at_rsi(df_ind, self.tp1_rsi)
                tp2_price = self.indicators.calculate_price_at_rsi(df_ind, self.tp2_rsi)
                tp3_price = self.indicators.calculate_price_at_rsi(df_ind, self.tp3_rsi)
                sl_price_raw = self.indicators.calculate_price_at_rsi(df_ind, 40)
                
                # Apply 0.3% buffer to SL
                sl_price = None
                if sl_price_raw is not None:
                    sl_price = sl_price_raw * Decimal(str(1 - self.sl_buffer_pct))

                # Register trade
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
                        }
                    )

                # Set waiting period
                self.context.set_waiting(
                    key,
                    seconds=self.cooldown_sec,
                    reason="BUY signal triggered - waiting",
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

            # Timeout check - if in CONFIRMING too long, reset
            # If RSI breaks significantly below WMA45, reset
            if rsi < rsi_wma45 - 5:
                self.context.transition(key, SCANNING, reason="RSI dropped too far below WMA45")

            return None

        # Safety reset for unknown states
        self.context.transition(key, SCANNING, reason="Unknown state reset")
        return None

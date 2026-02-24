"""
Layer 2: Core Logic - RSI WMA Retest Strategy (NO COOLDOWN / NO WAITING / NO SL LOCK)
===================================================================================
LONG ONLY strategy using TWO CHARTS:
- Price Chart: EMA21, EMA200, R40/R60/R70/R80 price levels
- RSI Chart: RSI, EMA9, WMA45

EXIT CHANGE (NO meta field needed):
- TP1: RSI >= 60  -> emit SELL with reason starting "TP1"
- TP2: RSI >= 70  -> emit SELL with reason starting "TP2"
- TP3: RSI >= 80  -> emit SELL with reason starting "TP3" (close all remaining)
"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from app.strategies.base import BaseStrategy
from app.utils.indicators import Indicators
from app.utils.resampler import resample_dataframe
from app.core.events import SignalEvent
from app.core.context import SCANNING, RETESTING, CONFIRMING


class RsiWmaRetestStrategy(BaseStrategy):
    """
    RSI WMA Retest Strategy - requires RSI to retest WMA45 before entry.
    """
    
    # Default configuration for this strategy
    DEFAULT_CONFIG = {
        # Indicator parameters
        "rsi_period": 14,
        "rsi_ema_length": 9,
        "rsi_wma_length": 45,
        "price_ema_fast": 21,
        "price_ema_slow": 200,
        
        # Entry conditions
        "wma_retest_distance": 0.3,  # Max distance for valid retest
        "rsi_floor": 40,              # No close below R40 during retest
        "wma45_min": 30,              # Class 1 signal minimum
        "wma45_max": 50,              # Class 1 signal maximum
        
        # H1 Filter
        "check_h1_wma45": True,
        "h1_wma45_min": 45.0,
        
        # TP levels (RSI values)
        "tp1_rsi": 60,
        "tp2_rsi": 70,
        "tp3_rsi": 80,
        
        # SL settings
        "sl_buffer_pct": 0.003,  # 0.3% buffer below R40
        "disaster_sl_multiplier": 3.0,  # Disaster SL = 3x the distance of Soft SL
        "candle_close_slippage_pct": 0.001,  # 0.1% slippage for candle-close exits

        # Trade management
        "use_active_trades": True,
    }

    def __init__(self, config: dict):
        super().__init__(config)

        # Use strategy defaults, allow override from config
        cfg = {**self.DEFAULT_CONFIG, **config.get("strategy_params", {})}
        bot_cfg = config.get("bot", {})

        self.timeframe = bot_cfg.get("timeframe", "1h")

        self.indicators = Indicators(
            rsi_length=cfg.get("rsi_period", 14),
            rsi_ema_length=cfg.get("rsi_ema_length", 9),
            rsi_wma_length=cfg.get("rsi_wma_length", 45),
            price_ema_fast=cfg.get("price_ema_fast", 21),
            price_ema_slow=cfg.get("price_ema_slow", 200),
        )

        # Retest threshold (RSI points)
        self.wma_retest_distance = float(cfg.get("wma_retest_distance", 0.3))

        # Filter: only trade when WMA45 < 50
        self.wma45_max = float(cfg.get("wma45_max", 50.0))

        # H1 Filter: WMA45 > 45 on H1
        self.check_h1_wma45 = bool(cfg.get("check_h1_wma45", True))
        self.h1_wma45_min = float(cfg.get("h1_wma45_min", 45.0))

        # TP ladder (by RSI)
        self.tp1_rsi = float(cfg.get("tp1_rsi", 60.0))
        self.tp2_rsi = float(cfg.get("tp2_rsi", 70.0))
        self.tp3_rsi = float(cfg.get("tp3_rsi", 80.0))

        # SL buffer (used to compute SL price from R40)
        self.sl_buffer_pct = float(cfg.get("sl_buffer_pct", 0.003))
        
        # Disaster SL multiplier (3x means disaster SL is 3x further than soft SL)
        self.disaster_sl_multiplier = float(cfg.get("disaster_sl_multiplier", 3.0))

        # Slippage for candle close exits
        self.candle_close_slippage_pct = float(cfg.get("candle_close_slippage_pct", 0.001))

        # Track one active trade per symbol
        self.use_active_trades = bool(cfg.get("use_active_trades", True))

        # Store R40 price at setup time (per symbol:timeframe)
        self._r40_price_at_retest: dict[str, Optional[Decimal]] = {}

    def _get_trade_meta(self, symbol: str) -> dict:
        trade = self.context.get_trade(symbol)
        if trade is None:
            return {}
        if trade.meta is None:
            trade.meta = {}
        return trade.meta

    def analyze(self, symbol: str, df) -> Optional[SignalEvent]:
        if df is None or len(df) < 220:
            return None

        # Only evaluate on closed candles
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

        prev = df_ind.iloc[-2] if len(df_ind) > 1 else None
        prev_close = prev.get("close") if prev is not None else None
        prev_ema21 = prev.get("ema21") if prev is not None else None

        ts = last.get("ts")
        if ts is None:
            try:
                ts = df.index[-1]
            except Exception:
                ts = None

        close_dec = Decimal(str(close)) if close is not None else Decimal("0")

        # ==================================================
        # EXIT: TP ladder (only if active trade exists)
        # ==================================================
        if self.use_active_trades and self.context.has_active_trade(symbol):
            meta = self._get_trade_meta(symbol)

            # -------------------------------------------------
            # Close by Candle SL: Check FIRST, before TP ladder
            # This allows graceful exit when candle close breaches Soft SL
            # -------------------------------------------------
            soft_sl = meta.get("soft_sl_price")
            if soft_sl is not None and close is not None:
                if close_dec <= soft_sl:
                    # Close the trade immediately
                    self.context.close_trade(symbol)
                    self.context.transition(key, SCANNING, reason="Close by Candle SL hit", now_ts=ts)
                    
                    # Apply slippage to simulate "next candle open" / real-world execution
                    # For SELL, price is lower by slippage
                    exec_price = close_dec * Decimal(str(1 - self.candle_close_slippage_pct))

                    return SignalEvent(
                        symbol=symbol,
                        signal_type="SELL",
                        price=exec_price,
                        timestamp=ts,
                        reason="CLOSE_BY_CANDLE_SL",
                    )

            tp1_hit = bool(meta.get("tp1_hit", False))
            tp2_hit = bool(meta.get("tp2_hit", False))
            tp3_hit = bool(meta.get("tp3_hit", False))

            # TP3: full exit
            if (not tp3_hit) and rsi >= self.tp3_rsi:
                meta["tp3_hit"] = True

                # close trade tracking now (portfolio will close remaining)
                self.context.close_trade(symbol)
                self.context.transition(key, SCANNING, reason="TP3 hit -> full exit", now_ts=ts)

                return SignalEvent(
                    symbol=symbol,
                    signal_type="SELL",
                    price=close_dec,
                    timestamp=ts,
                    reason=f"TP3 RSI>={self.tp3_rsi} (RSI={rsi:.2f})",
                )

            # TP2: partial exit
            if (not tp2_hit) and rsi >= self.tp2_rsi:
                meta["tp2_hit"] = True
                return SignalEvent(
                    symbol=symbol,
                    signal_type="SELL",
                    price=close_dec,
                    timestamp=ts,
                    reason=f"TP2 RSI>={self.tp2_rsi} (RSI={rsi:.2f})",
                )

            # TP1: partial exit
            if (not tp1_hit) and rsi >= self.tp1_rsi:
                meta["tp1_hit"] = True
                return SignalEvent(
                    symbol=symbol,
                    signal_type="SELL",
                    price=close_dec,
                    timestamp=ts,
                    reason=f"TP1 RSI>={self.tp1_rsi} (RSI={rsi:.2f})",
                )

            # While trade is open, do not search BUY
            return None

        # ==================================================
        # ENTRY: state machine
        # ==================================================
        state = self.context.get_state(key)

        # STATE 1: SCANNING
        if state.phase == SCANNING:
            if (
                rsi_ema9 is not None
                and rsi_wma45 is not None
                and close is not None
                and rsi > rsi_ema9
                and rsi > rsi_wma45
                and rsi_ema9 > rsi_wma45
            ):
                r40_price = self.indicators.calculate_price_at_rsi(df_ind, 40)
                self._r40_price_at_retest[key] = r40_price
                self.context.transition(key, RETESTING, reason="Setup valid - watching retest", now_ts=ts)
            return None

        # STATE 2: RETESTING
        if state.phase == RETESTING:
            if rsi_wma45 is None:
                return None

            r40_price = self._r40_price_at_retest.get(key)
            if r40_price is not None and close is not None:
                if Decimal(str(close)) < r40_price:
                    self.context.transition(key, SCANNING, reason="Price closed below R40 level", now_ts=ts)
                    return None

            distance = abs(rsi - rsi_wma45)
            if distance <= self.wma_retest_distance:
                state.retest_touched_ts = ts
                self.context.transition(key, CONFIRMING, reason=f"RSI retested WMA45 (dist={distance:.2f})", now_ts=ts)
            return None

        # STATE 3: CONFIRMING
        if state.phase == CONFIRMING:
            if close is None or ema21 is None or rsi_wma45 is None:
                return None
            if prev_close is None or prev_ema21 is None:
                return None

            crossed_up = (prev_close <= prev_ema21) and (close > ema21)
            rsi_bounced = (rsi > rsi_wma45) and (rsi > rsi_ema9)

            if crossed_up and rsi_bounced:
                # Only trade when WMA45 < 50
                if rsi_wma45 >= self.wma45_max:
                    self.context.transition(
                        key,
                        SCANNING,
                        reason=f"WMA45 too high ({rsi_wma45:.1f} >= {self.wma45_max})",
                        now_ts=ts,
                    )
                    return None

                # Check H1 condition: WMA45 > 45
                if self.check_h1_wma45:
                    # Resample to H1
                    df_h1 = resample_dataframe(df, "1h")
                    if not df_h1.empty:
                        # Compute indicators on H1
                        df_h1_ind = self.indicators.compute(df_h1, symbol=symbol, timeframe="1h")
                        last_h1 = Indicators.last(df_h1_ind)
                        h1_rsi_wma45 = last_h1.get("rsi_wma45")

                        if h1_rsi_wma45 is None or h1_rsi_wma45 <= self.h1_wma45_min:
                            # Log and transition to SCANNING
                            wma_val = f"{h1_rsi_wma45:.2f}" if h1_rsi_wma45 is not None else "None"
                            self.context.transition(
                                key,
                                SCANNING,
                                reason=f"H1 WMA45 too low ({wma_val} <= {self.h1_wma45_min})",
                                now_ts=ts,
                            )
                            return None

                # Compute TP/SL prices for PortfolioManager
                tp1_price = self.indicators.calculate_price_at_rsi(df_ind, self.tp1_rsi)
                tp2_price = self.indicators.calculate_price_at_rsi(df_ind, self.tp2_rsi)
                tp3_price = self.indicators.calculate_price_at_rsi(df_ind, self.tp3_rsi)
                sl_price_raw = self.indicators.calculate_price_at_rsi(df_ind, 40)

                # -------------------------------------------------
                # Dual SL System:
                # 1. Soft SL: R40 - buffer (for candle-close exit logic)
                # 2. Disaster SL: 3x distance from entry (hard limit order)
                # -------------------------------------------------
                soft_sl_price = None
                disaster_sl_price = None
                
                if sl_price_raw is not None:
                    soft_sl_price = sl_price_raw * Decimal(str(1 - self.sl_buffer_pct))
                    
                    # Calculate Disaster SL at multiplier x distance from entry
                    entry_price = Decimal(str(close))
                    soft_sl_distance = entry_price - soft_sl_price
                    disaster_sl_price = entry_price - (soft_sl_distance * Decimal(str(self.disaster_sl_multiplier)))

                # Register trade
                if self.use_active_trades:
                    self.context.open_trade(
                        symbol=symbol,
                        timeframe=self.timeframe,
                        side="LONG",
                        entry_price=float(ema21),
                        meta={
                            "tp1_price": tp1_price,
                            "tp2_price": tp2_price,
                            "tp3_price": tp3_price,
                            "soft_sl_price": soft_sl_price,  # For candle-close checking
                            "disaster_sl_price": disaster_sl_price,  # Reference only
                            "tp1_hit": False,
                            "tp2_hit": False,
                            "tp3_hit": False,
                        },
                        now_ts=ts,
                    )

                # Reset scan after BUY
                self.context.transition(key, SCANNING, reason="BUY emitted, reset scan", now_ts=ts)
                self._r40_price_at_retest.pop(key, None)

                return SignalEvent(
                    symbol=symbol,
                    signal_type="BUY",
                    price=Decimal(str(close)),
                    timestamp=ts,
                    reason=f"BUY Retest confirmed + EMA21 crossup (WMA45={rsi_wma45:.1f})",
                    tp1_price=tp1_price,
                    tp2_price=tp2_price,
                    tp3_price=tp3_price,
                    sl_price=disaster_sl_price,  # Hard limit order on exchange
                    soft_sl_price=soft_sl_price,  # For portfolio reference
                    signal_class=1,
                )

            # Reset if RSI collapses too far under WMA45
            if rsi_wma45 is not None and rsi < rsi_wma45 - 2:
                self.context.transition(key, SCANNING, reason="RSI fell below WMA45 too far", now_ts=ts)

            return None

        # Safety reset
        self.context.transition(key, SCANNING, reason="Unknown state reset", now_ts=ts)
        return None

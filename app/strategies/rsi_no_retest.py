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

from dataclasses import dataclass, fields as dc_fields
from decimal import Decimal
from typing import Optional, Any

import pandas as pd
import structlog

from app.strategies.base import BaseStrategy
from app.utils.indicators import Indicators
from app.utils.resampler import resample_dataframe
from app.core.context import SCANNING, CONFIRMING
from app.core.snapshots import PositionSnapshot, ContextSnapshot
from app.core.analysis_result import AnalysisResult
from app.core.actions import OpenPosition, ClosePosition, MoveSL, DoNothing

logger = structlog.get_logger()


@dataclass(frozen=True)
class RsiNoRetestConfig:
    """Typed config for RsiNoRetestStrategy. Constructed from strategy_params dict."""

    rsi_period: int = 21
    rsi_ema_length: int = 9
    rsi_wma_length: int = 45
    price_ema_fast: int = 21
    price_ema_slow: int = 200
    nr_lookback: int = 30
    nr_max_above_ema21: int = 3
    nr_rsi_spread_min: float = 2.5
    nr_sl_mode: str = "lowest_close"
    sl_buffer_pct: float = 0.0
    disaster_sl_multiplier: float = 3.0
    candle_close_slippage_pct: float = 0.0
    nr_tp1_rr: float = 1.0
    nr_tp2_rr: float = 2.0
    nr_tp3_rr: float = 3.0
    nr_tp_count: int = 3
    tp1_close_pct: float = 0.50
    tp2_close_pct: float = 0.50
    tp3_close_pct: float = 0.0
    nr_move_sl_rr: float = 0.5
    nr_lock_profit_rr: float = 0.2
    use_active_trades: bool = True

    @classmethod
    def from_dict(cls, params: dict) -> "RsiNoRetestConfig":
        """Construct from strategy_params dict, ignoring unknown keys."""
        valid_keys = {f.name for f in dc_fields(cls)}
        filtered = {k: v for k, v in params.items() if k in valid_keys}
        return cls(**filtered)


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
        "nr_max_above_ema21": 3,     # Max candles above EMA21 in lookback (0 = strict)
        "nr_rsi_spread_min": 2.5,    # Min RSI_EMA9 - RSI_WMA45 spread
        
        # SL settings
        "nr_sl_mode": "lowest_close",    # "rsi_ema9" or "lowest_wick"
        "sl_buffer_pct": 0.0,            # No buffer (original behavior)
        "disaster_sl_multiplier": 3.0,   # Disaster SL = 2x distance from entry
        "candle_close_slippage_pct": 0,  # 0.1% slippage for candle-close exits
        
        # TP settings
        "nr_tp1_rr": 1.0,            # TP1: 1R (Close 50%)
        "nr_tp2_rr": 2.0,            # TP2: 2R (Close 25%)
        "nr_tp3_rr": 3.0,            # TP3: 3R (Close 25%)
        "nr_tp_count": 3,            # Number of TPs (1-3)
        "tp1_close_pct": 0.50,
        "tp2_close_pct": 0.5,
        "tp3_close_pct": 0,

        # SL management
        "nr_move_sl_rr": 0.5,        # Trigger: move SL when high reaches 0.5R (halfway to TP1)
        "nr_lock_profit_rr": 0.2,    # New SL level: 0.2R above entry (lock 20% of profit)

        # Trade management
        "use_active_trades": True,
    }

    def __init__(self, config: dict):
        super().__init__(config)

        # Use strategy defaults, allow override from config
        from app.core.config import AppConfig
        strategy_params = (
            config.strategy_params
            if isinstance(config, AppConfig)
            else config.get("strategy_params", {})
        ) or {}
        cfg = {**self.DEFAULT_CONFIG, **strategy_params}
        self.strategy_cfg = RsiNoRetestConfig.from_dict(cfg)
        bot_cfg = config.get("bot", {}) if not isinstance(config, AppConfig) else {}

        # Try top-level first, then bot-level
        self.timeframe = config.get("timeframe", "15m")
        if not self.timeframe:
            self.timeframe = bot_cfg.get("timeframe", "15m")

        self.indicators = Indicators(
            rsi_length=cfg.get("rsi_period", 14),
            rsi_ema_length=cfg.get("rsi_ema_length", 9),
            rsi_wma_length=cfg.get("rsi_wma_length", 45),
            price_ema_fast=cfg.get("price_ema_fast", 21),
            price_ema_slow=cfg.get("price_ema_slow", 200),
        )

        risk_cfg = config.get("risk", {}) if not hasattr(config, "get") or isinstance(config, dict) else getattr(config, "risk", {})
        if not isinstance(risk_cfg, dict):
             risk_cfg = risk_cfg.dict() if hasattr(risk_cfg, "dict") else {}
             
        self.taker_fee = Decimal(str(risk_cfg.get("taker_fee", 0.0005)))
        self.maker_fee = Decimal(str(risk_cfg.get("maker_fee", 0.0002)))

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

        self.tp_count = int(cfg.get("nr_tp_count", 3))
        self.tp1_close_pct = float(cfg.get("tp1_close_pct", 0.5))
        self.tp2_close_pct = float(cfg.get("tp2_close_pct", 0.5))

        # NEW: Move SL trigger and lock level
        self.move_sl_rr = Decimal(str(cfg.get("nr_move_sl_rr", 0.5)))       # Trigger at 0.5R
        self.lock_profit_rr = Decimal(str(cfg.get("nr_lock_profit_rr", 0.2))) # Lock 20% profit
        self.use_active_trades = bool(cfg.get("use_active_trades", True))
        
        # Debug Toggle
        self.debug_enabled = bool(bot_cfg.get("debug", False))

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
        if len(df_ind) < 3:
            return False
            
        # We want to check if the PREVIOUS candle (index -2, the one that just closed)
        # crossed above the EMA.
        # So we compare -3 (Prior) vs -2 (Confirmed Close).
        
        confirmed_close_candle = df_ind.iloc[-2]
        prior_candle = df_ind.iloc[-3]
        
        # Values for Candle -2 (Confirmed Reclaim Candidate)
        curr_close = confirmed_close_candle.get("close")
        curr_ema21 = confirmed_close_candle.get("ema21")
        
        # Values for Candle -3 (Prior Context)
        prior_close = prior_candle.get("close")
        prior_ema21 = prior_candle.get("ema21")
        
        if curr_close is None or curr_ema21 is None or prior_close is None or prior_ema21 is None:
            return False

        # if self.debug_enabled:
        ts_prior = prior_candle.name if hasattr(prior_candle, "name") else "N/A"
        ts_closed = confirmed_close_candle.name if hasattr(confirmed_close_candle, "name") else "N/A"
        if self.debug_enabled:
            logger.debug(f"DEBUG RECLAIM: Prior(-3)={prior_close}/{prior_ema21} (TS={ts_prior}) | Closed(-2)={curr_close}/{curr_ema21} (TS={ts_closed})")

        # Logic: Prior (-3) was BELOW/EQUAL, and Confirmed Closed (-2) is ABOVE.
        return (prior_close <= prior_ema21) and (curr_close > curr_ema21)

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

    def _compute_price_at_rr(self, entry: Decimal, sl: Decimal, rr: Decimal, is_taker_exit: bool = False) -> Optional[Decimal]:
        """
        Calculates the target price to achieve exactly `rr` * R, net of fees.
        R is the risk defined as (entry - sl).
        Net Profit = exit - entry - entry * taker_fee - exit * exit_fee.
        So: exit * (1 - exit_fee) = entry * (1 + taker_fee) + (rr * R)
        """
        risk = entry - sl
        if risk <= Decimal("0"):
            return None
            
        target_net_profit = rr * risk
        exit_fee_rate = self.taker_fee if is_taker_exit else self.maker_fee
        
        target_price = (entry * (Decimal("1") + self.taker_fee) + target_net_profit) / (Decimal("1") - exit_fee_rate)
        return target_price

    # ---------------- main ----------------
    def analyze(
        self,
        symbol: str,
        df,
        position: Optional[PositionSnapshot] = None,
        context: Optional[ContextSnapshot] = None,
    ) -> AnalysisResult:
        # Canonical defaults
        if context is None:
            context = ContextSnapshot(state=SCANNING)

        _noop = AnalysisResult(actions=[DoNothing()], new_context=context)

        if df is None or len(df) < max(220, self.lookback + 10):
            return _noop

        if "closed" in df.columns and not bool(df.iloc[-1]["closed"]):
            return _noop

        # optional resample hook
        df_tf = resample_dataframe(df, self.timeframe) if "timestamp" in getattr(df, "columns", []) else df

        df_ind = self.indicators.compute(df_tf, symbol=symbol, timeframe=self.timeframe)
        last = Indicators.last(df_ind)
        if not last:
            return _noop

        # prices (Decimals)
        close = self._to_dec(last.get("close"))
        high = self._to_dec(last.get("high"))
        open_price = self._to_dec(last.get("open"))
        ema21 = self._to_dec(last.get("ema21"))

        if close is None or ema21 is None:
            return _noop

        # RSI values
        rsi_ema9 = last.get("rsi_ema9")
        rsi_wma45 = last.get("rsi_wma45")

        # -------------------------
        # EXIT / MANAGEMENT (position is open)
        # -------------------------
        if self.use_active_trades and position and position.has_position:
            meta = dict(context.meta)  # mutable copy — never mutate context.meta directly

            entry_price = self._to_dec(meta.get("entry_price"))
            if entry_price is None:
                return _noop

            # Soft SL: prefer the ContextSnapshot direct field, fall back to meta
            soft_sl = context.soft_sl_price or self._to_dec(meta.get("soft_sl_price"))
            original_soft_sl = self._to_dec(meta.get("original_soft_sl")) or soft_sl

            moved_sl = bool(meta.get("moved_sl_to_entry", False))
            pending_candle_sl = bool(meta.get("pending_candle_sl", False))

            # Lock profit price: precompute from original SL (never changes)
            lock_profit_price = self._to_dec(meta.get("lock_profit_price"))
            if lock_profit_price is None and original_soft_sl and entry_price:
                # Stop loss acts as a TAKER order when hit
                lock_profit_price = self._compute_price_at_rr(entry_price, original_soft_sl, self.lock_profit_rr, is_taker_exit=True)

            # -------------------------------------------------
            # STEP 0: pending candle SL — exit at THIS candle's open
            # -------------------------------------------------
            if pending_candle_sl and open_price is not None:
                new_ctx = ContextSnapshot(state=SCANNING)
                return AnalysisResult(
                    actions=[ClosePosition(symbol=symbol, reason="CLOSE_BY_CANDLE_SL", price=open_price)],
                    new_context=new_ctx,
                )

            # -------------------------------------------------
            # STEP 1: Move SL to lock profit when high reaches +0.5R
            # TP targets are handled entirely by the exchange as limit orders.
            # -------------------------------------------------
            if (not moved_sl) and high is not None and soft_sl is not None:
                move_trigger = self._compute_price_at_rr(entry_price, original_soft_sl, self.move_sl_rr, is_taker_exit=False)
                if move_trigger is not None and high >= move_trigger and lock_profit_price is not None:
                    new_meta = dict(meta)
                    new_meta["moved_sl_to_entry"] = True
                    new_meta["sl_price"] = lock_profit_price
                    new_meta["soft_sl_price"] = lock_profit_price
                    new_ctx = ContextSnapshot(
                        state=context.state,
                        soft_sl_price=lock_profit_price,
                        meta=new_meta,
                    )
                    return AnalysisResult(
                        actions=[MoveSL(
                            symbol=symbol,
                            new_sl_price=lock_profit_price,
                            reason=f"MOVE_SL_LOCK_PROFIT (high={high} >= {move_trigger} = +{self.move_sl_rr}R, new_sl={lock_profit_price} = +{self.lock_profit_rr}R)",
                        )],
                        new_context=new_ctx,
                    )

            # -------------------------------------------------
            # STEP 2: Candle-close SL — set flag, exit next candle's open
            # -------------------------------------------------
            if soft_sl is not None and close is not None and close <= soft_sl:
                new_meta = dict(meta)
                new_meta["pending_candle_sl"] = True
                new_ctx = ContextSnapshot(state=context.state, soft_sl_price=soft_sl, meta=new_meta)
                return AnalysisResult(actions=[DoNothing()], new_context=new_ctx)

            return _noop

        # -------------------------
        # Entry state machine (no open position)
        # -------------------------
        if self.debug_enabled:
            logger.debug(f"[{symbol}] DEBUG: State={context.state}, OHLCV Size={len(df)}")

        current_state = context.state

        if current_state == SCANNING:
            if not self._detect_reclaim(df_ind):
                if self.debug_enabled:
                    logger.debug(f"[{symbol}] DEBUG: Reclaim not detected.")
                return _noop

            if not self._pullback_filter(df_ind):
                if self.debug_enabled:
                    logger.debug(f"[{symbol}] DEBUG: Reclaim detected but failed Pullback Filter.")
                return _noop

            if self.debug_enabled:
                logger.debug(f"[{symbol}] DEBUG: Transition to CONFIRMING (Reclaim OK)")
            # Transition within the same tick (fall through to CONFIRMING)
            current_state = CONFIRMING

        if current_state == CONFIRMING:
            if rsi_ema9 is None or rsi_wma45 is None:
                new_ctx = ContextSnapshot(state=CONFIRMING, meta=dict(context.meta))
                return AnalysisResult(actions=[DoNothing()], new_context=new_ctx)

            spread = float(rsi_ema9) - float(rsi_wma45)
            if spread < self.rsi_spread_min:
                if self.debug_enabled:
                    logger.debug(f"[{symbol}] DEBUG: Failed Confirmation - Spread {spread:.2f} < {self.rsi_spread_min} - Reset to SCANNING")
                return AnalysisResult(actions=[DoNothing()], new_context=ContextSnapshot(state=SCANNING))

            # Compute SL
            sl_price = self._compute_sl(df_ind)
            if sl_price is None:
                self.sl_mode = "lowest_wick"
                sl_price = self._compute_sl(df_ind)

            if sl_price is None:
                if self.debug_enabled:
                    logger.debug(f"[{symbol}] DEBUG: Failed Confirmation - No SL computed - Reset to SCANNING")
                return AnalysisResult(actions=[DoNothing()], new_context=ContextSnapshot(state=SCANNING))

            entry_price = close

            # TPs are limit orders => Maker fees
            tp1_price = self._compute_price_at_rr(entry_price, sl_price, self.tp1_rr, is_taker_exit=False)
            tp2_price = self._compute_price_at_rr(entry_price, sl_price, self.tp2_rr, is_taker_exit=False)
            tp3_price = self._compute_price_at_rr(entry_price, sl_price, self.tp3_rr, is_taker_exit=False)

            # Dynamic TP allocations
            tp_allocations = {}
            if self.tp_count == 1:
                tp_allocations["TP1"] = 1.0
                tp2_price = None
                tp3_price = None
            elif self.tp_count == 2:
                tp_allocations["TP1"] = self.tp1_close_pct
                tp_allocations["TP2"] = 1.0
                tp3_price = None
            else:
                tp_allocations["TP1"] = self.tp1_close_pct
                tp_allocations["TP2"] = self.tp2_close_pct if self.tp2_close_pct < 1.0 else 0.5
                tp_allocations["TP3"] = 1.0

            if tp1_price is None:
                if self.debug_enabled:
                    logger.debug(f"[{symbol}] DEBUG: Failed Confirmation - Invalid TP - Reset to SCANNING")
                return AnalysisResult(actions=[DoNothing()], new_context=ContextSnapshot(state=SCANNING))

            # Dual SL system
            soft_sl_price = sl_price
            disaster_sl_price = None
            if soft_sl_price is not None:
                soft_sl_distance = entry_price - soft_sl_price
                disaster_sl_price = entry_price - (soft_sl_distance * Decimal(str(self.disaster_sl_multiplier)))

            # Lock profit is triggered as STOP_MARKET => Taker fee
            lock_profit_price = self._compute_price_at_rr(entry_price, soft_sl_price, self.lock_profit_rr, is_taker_exit=True)

            # Build new context carrying the active trade metadata
            tp_prices = [p for p in [tp1_price, tp2_price, tp3_price] if p is not None]
            new_meta = {
                "entry_price": entry_price,
                "sl_price": soft_sl_price,
                "soft_sl_price": soft_sl_price,
                "original_soft_sl": soft_sl_price,  # never modified — used for lock_profit calc
                "disaster_sl_price": disaster_sl_price,
                "tp1_price": tp1_price,
                "tp2_price": tp2_price,
                "tp3_price": tp3_price,
                "lock_profit_price": lock_profit_price,
                "moved_sl_to_entry": False,
                "pending_candle_sl": False,
                "rsi_spread": spread,
                "sl_mode": self.sl_mode,
                "tp_allocations": tp_allocations,
            }
            # State goes back to SCANNING after emitting entry
            new_ctx = ContextSnapshot(state=SCANNING, soft_sl_price=soft_sl_price, meta=new_meta)

            logger.info(f"[{symbol}] DEBUG: BUY SIGNAL GENERATED @ {entry_price} (SL={disaster_sl_price})")

            return AnalysisResult(
                actions=[OpenPosition(
                    symbol=symbol,
                    side="BUY",
                    entry_price=entry_price,
                    sl_price=disaster_sl_price,
                    soft_sl_price=soft_sl_price,
                    tp_prices=tp_prices,
                    tp_allocations=tp_allocations,
                    lock_profit_price=lock_profit_price,
                    signal_class=2,
                    reason=f"NO-RETEST BUY (spread={spread:.2f} >= {self.rsi_spread_min})",
                )],
                new_context=new_ctx,
            )

        return AnalysisResult(actions=[DoNothing()], new_context=ContextSnapshot(state=SCANNING))

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

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional, Any

import pandas as pd
import structlog

from app.trading.strategy.base import BaseStrategy
from app.trading.strategy.utils.config_helpers import merge_config
from app.trading.strategy.utils.sl_tp_builders import build_tp_allocations
from app.data.indicators import Indicators
from app.data.resampler import resample_dataframe
from app.core.context import SCANNING, CONFIRMING
from app.core.snapshots import PositionSnapshot, ContextSnapshot
from app.core.analysis_result import AnalysisResult
from app.core.actions import OpenPosition, ClosePosition, MoveSL, DoNothing
from app.core.constants import DEFAULT_TAKER_FEE_DECIMAL, DEFAULT_MAKER_FEE_DECIMAL, WARMUP
from app.core.utils import to_decimal_or_none

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

    # Construction via merge_config from app.trading.strategy.utils


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
        "nr_tp_count": 1,            # Number of TPs (1-3)
        "tp1_close_pct": 1,
        "tp2_close_pct": 0,
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
        self.strategy_cfg = merge_config(RsiNoRetestConfig, cfg)
        bot_cfg = config.get("bot", {}) if not isinstance(config, AppConfig) else {}

        # Try top-level first, then bot-level
        self.timeframe = config.get("timeframe", "15m")
        if not self.timeframe:
            self.timeframe = bot_cfg.get("timeframe", "15m")

        self.indicators = Indicators(
            rsi_period=cfg.get("rsi_period", 14),
            rsi_ema_period=cfg.get("rsi_ema_length", 9),
            rsi_wma_period=cfg.get("rsi_wma_length", 45),
            price_ema_fast=cfg.get("price_ema_fast", 21),
            price_ema_slow=cfg.get("price_ema_slow", 200),
            include_price_emas=True,
        )

        risk_cfg = config.get("risk", {}) if not hasattr(config, "get") or isinstance(config, dict) else getattr(config, "risk", {})
        if not isinstance(risk_cfg, dict):
             risk_cfg = risk_cfg.dict() if hasattr(risk_cfg, "dict") else {}
             
        self.taker_fee = Decimal(str(risk_cfg.get("taker_fee", DEFAULT_TAKER_FEE_DECIMAL)))
        self.maker_fee = Decimal(str(risk_cfg.get("maker_fee", DEFAULT_MAKER_FEE_DECIMAL)))

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

        # Per-candle debug rows — accumulated during backtest, exported via export_debug_csv()
        self._debug_rows: list[dict] = []

    # ---------------- helpers ----------------
    def _ts_from_last(self, df: pd.DataFrame, last: dict) -> Any:
        ts = last.get("ts")
        if ts is None:
            try:
                return df.index[-1]
            except Exception:
                return None
        return ts

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

    def _pullback_filter(self, df_ind: pd.DataFrame) -> tuple[bool, int]:
        """
        Lookback excludes current candle.
        Condition: number of candles closed above EMA21 <= max_above_ema21
        Returns (passed, above_count).
        """
        if len(df_ind) < self.lookback + 2:
            return False, 0
        window = df_ind.iloc[-(self.lookback + 1) : -1]
        closes = window["close"]
        ema21s = window["ema21"]
        above = int((closes > ema21s).sum())
        return above <= self.max_above_ema21, above

    def export_debug_csv(self, path: str) -> None:
        """Export per-candle debug rows collected during backtest to a CSV file."""
        if not self._debug_rows:
            return
        import os
        os.makedirs(os.path.dirname(path), exist_ok=True)
        pd.DataFrame(self._debug_rows).to_csv(path, index=False)

    def _compute_sl(self, df_ind: pd.DataFrame) -> Optional[Decimal]:
        if self.sl_mode == "lowest_wick":
            window = df_ind.iloc[-(self.lookback + 1) : -1]
            if "low" not in window.columns:
                return None
            sl = to_decimal_or_none(window["low"].min())
        elif self.sl_mode == "lowest_close":
            window = df_ind.iloc[-(self.lookback + 1) : -1]
            if "close" not in window.columns:
                return None
            sl = to_decimal_or_none(window["close"].min())
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

        if df is None or len(df) < max(WARMUP, self.lookback + 10):
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
        close = to_decimal_or_none(last.get("close"))
        high = to_decimal_or_none(last.get("high"))
        open_price = to_decimal_or_none(last.get("open"))
        ema21 = to_decimal_or_none(last.get("ema21"))

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

            entry_price = to_decimal_or_none(meta.get("entry_price"))
            if entry_price is None:
                return _noop

            # Soft SL: prefer the ContextSnapshot direct field, fall back to meta
            soft_sl = context.soft_sl_price or to_decimal_or_none(meta.get("soft_sl_price"))
            original_soft_sl = to_decimal_or_none(meta.get("original_soft_sl")) or soft_sl

            moved_sl = bool(meta.get("moved_sl_to_entry", False))
            pending_candle_sl = bool(meta.get("pending_candle_sl", False))

            # Lock profit price: precompute from original SL (never changes)
            lock_profit_price = to_decimal_or_none(meta.get("lock_profit_price"))
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

        # Initialise a debug row for this candle (entry-path only)
        # Use index[-1] (current candle = entry candle) so it matches round_trip entry_time
        _ts = str(df_ind.index[-1]) if len(df_ind) >= 1 else None
        _debug_row: dict = {
            "timestamp": _ts,
            "symbol": symbol,
            "close": float(close) if close is not None else None,
            "ema21": float(ema21) if ema21 is not None else None,
            "rsi_ema9": float(rsi_ema9) if rsi_ema9 is not None else None,
            "rsi_wma45": float(rsi_wma45) if rsi_wma45 is not None else None,
            "spread": None,
            "above_count": None,
            "max_above_ema21": self.max_above_ema21,
            "rsi_spread_min": self.rsi_spread_min,
            "reclaim_detected": False,
            "pullback_ok": False,
            "spread_ok": False,
            "signal": "NONE",
        }

        if current_state == SCANNING:
            if not self._detect_reclaim(df_ind):
                if self.debug_enabled:
                    logger.debug(f"[{symbol}] DEBUG: Reclaim not detected.")
                self._debug_rows.append(_debug_row)
                return _noop

            _debug_row["reclaim_detected"] = True
            pullback_ok, above_count = self._pullback_filter(df_ind)
            _debug_row["above_count"] = above_count
            _debug_row["pullback_ok"] = pullback_ok

            if not pullback_ok:
                if self.debug_enabled:
                    logger.debug(
                        f"[{symbol}] DEBUG: Reclaim detected but failed Pullback Filter "
                        f"(above={above_count} > max_above_ema21={self.max_above_ema21})."
                    )
                self._debug_rows.append(_debug_row)
                return _noop

            if self.debug_enabled:
                logger.debug(
                    f"[{symbol}] DEBUG: Transition to CONFIRMING (Reclaim OK, above={above_count}/{self.max_above_ema21})"
                )
            # Transition within the same tick (fall through to CONFIRMING)
            current_state = CONFIRMING

        if current_state == CONFIRMING:
            if rsi_ema9 is None or rsi_wma45 is None:
                new_ctx = ContextSnapshot(state=CONFIRMING, meta=dict(context.meta))
                self._debug_rows.append(_debug_row)
                return AnalysisResult(actions=[DoNothing()], new_context=new_ctx)

            spread = float(rsi_ema9) - float(rsi_wma45)
            _debug_row["spread"] = spread
            if spread < self.rsi_spread_min:
                if self.debug_enabled:
                    logger.debug(
                        f"[{symbol}] DEBUG: Failed Confirmation - "
                        f"RSI_EMA9={float(rsi_ema9):.2f}, RSI_WMA45={float(rsi_wma45):.2f}, "
                        f"Spread={spread:.2f} < rsi_spread_min={self.rsi_spread_min} - Reset to SCANNING"
                    )
                self._debug_rows.append(_debug_row)
                return AnalysisResult(actions=[DoNothing()], new_context=ContextSnapshot(state=SCANNING))

            _debug_row["spread_ok"] = True

            # Compute SL
            sl_price = self._compute_sl(df_ind)
            if sl_price is None:
                self.sl_mode = "lowest_wick"
                sl_price = self._compute_sl(df_ind)

            if sl_price is None:
                if self.debug_enabled:
                    logger.debug(f"[{symbol}] DEBUG: Failed Confirmation - No SL computed - Reset to SCANNING")
                self._debug_rows.append(_debug_row)
                return AnalysisResult(actions=[DoNothing()], new_context=ContextSnapshot(state=SCANNING))

            entry_price = close

            # TPs are limit orders => Maker fees
            tp1_price = self._compute_price_at_rr(entry_price, sl_price, self.tp1_rr, is_taker_exit=False)
            tp2_price = self._compute_price_at_rr(entry_price, sl_price, self.tp2_rr, is_taker_exit=False)
            tp3_price = self._compute_price_at_rr(entry_price, sl_price, self.tp3_rr, is_taker_exit=False)

            # Dynamic TP allocations
            tp2_pct = self.tp2_close_pct if self.tp2_close_pct < 1.0 else 0.5
            tp_allocations = build_tp_allocations(self.tp_count, self.tp1_close_pct, tp2_pct)
            if self.tp_count == 1:
                tp2_price = None
                tp3_price = None
            elif self.tp_count == 2:
                tp3_price = None

            if tp1_price is None:
                if self.debug_enabled:
                    logger.debug(f"[{symbol}] DEBUG: Failed Confirmation - Invalid TP - Reset to SCANNING")
                self._debug_rows.append(_debug_row)
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

            logger.info(
                f"[{symbol}] DEBUG: BUY SIGNAL GENERATED @ {entry_price} "
                f"(SL={disaster_sl_price}, RSI_EMA9={float(rsi_ema9):.2f}, RSI_WMA45={float(rsi_wma45):.2f}, Spread={spread:.2f})"
            )

            _debug_row["signal"] = "BUY"
            self._debug_rows.append(_debug_row)

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

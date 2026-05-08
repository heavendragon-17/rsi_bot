# app/trading/strategy/rsi_no_retest/strategy.py
"""
Layer 2: Core Logic - RSI No Retest Strategy (Entry reclaim EMA21)
==================================================================

Thin orchestrator: dispatches to the package's ``entry`` and ``exit``
submodules for the actual state-machine logic.

Rules (summary):
- Entry: first candle closing > EMA21 (cross up) after prolonged decline
- RSI confirmation: (RSI_EMA9 - RSI_WMA45) >= rsi_spread_min
- SL: configurable mode (rsi_ema9 / lowest_wick / lowest_close)
- TP: 1-3 levels at configurable RR ratios
- Exit: candle-close SL, lock-profit trigger, pending candle SL
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pandas as pd
import structlog

from app.core.actions import DoNothing
from app.core.analysis_result import AnalysisResult
from app.core.constants import (
    DEFAULT_MAKER_FEE_DECIMAL,
    DEFAULT_TAKER_FEE_DECIMAL,
    SL_TRIGGER_CANDLE_CLOSE,
    SL_TRIGGER_MODES,
    WARMUP,
)
from app.core.context import SCANNING
from app.core.snapshots import ContextSnapshot, PositionSnapshot
from app.core.utils import to_decimal_or_none
from app.data.indicators import Indicators
from app.data.resampler import resample_dataframe
from app.trading.strategy.base import BaseStrategy
from app.trading.strategy.rsi_no_retest.entry import check_entry
from app.trading.strategy.rsi_no_retest.exit import manage_exit
from app.trading.strategy.utils.config_helpers import merge_config
from app.trading.strategy.utils.param_metadata import (
    RSI_NO_RETEST_GROUPS,
    RSI_NO_RETEST_METADATA,
)
from app.trading.strategy.utils.schema_helper import SchemaConfigMixin

logger = structlog.get_logger()


@dataclass(frozen=True)
class RsiNoRetestConfig(SchemaConfigMixin):
    """Typed config for RsiNoRetestStrategy. Constructed from strategy_params dict."""

    METADATA = RSI_NO_RETEST_METADATA
    UI_GROUPS = RSI_NO_RETEST_GROUPS

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
    sl_trigger_mode: str = SL_TRIGGER_CANDLE_CLOSE
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
    max_holding_enabled: bool = True
    max_holding_bars: int = 96
    use_active_trades: bool = True


class RsiNoRetestStrategy(BaseStrategy):
    """
    RSI No Retest Strategy - enters on EMA21 reclaim without requiring RSI retest.
    """

    CONFIG_CLASS = RsiNoRetestConfig

    # Default configuration for this strategy
    DEFAULT_CONFIG = {
        "rsi_period": 21,
        "rsi_ema_length": 9,
        "rsi_wma_length": 45,
        "price_ema_fast": 21,
        "price_ema_slow": 200,
        "nr_lookback": 30,
        "nr_max_above_ema21": 3,
        "nr_rsi_spread_min": 2.5,
        "nr_sl_mode": "lowest_close",
        "sl_buffer_pct": 0.0,
        "disaster_sl_multiplier": 3.0,
        "sl_trigger_mode": SL_TRIGGER_CANDLE_CLOSE,
        "candle_close_slippage_pct": 0,
        "nr_tp1_rr": 1.0,
        "nr_tp2_rr": 2.0,
        "nr_tp3_rr": 3.0,
        "nr_tp_count": 1,
        "tp1_close_pct": 1,
        "tp2_close_pct": 0,
        "tp3_close_pct": 0,
        "nr_move_sl_rr": 0.5,
        "nr_lock_profit_rr": 0.2,
        "max_holding_enabled": True,
        "max_holding_bars": 96,
        "use_active_trades": True,
    }

    def __init__(self, config: dict):
        super().__init__(config)

        from app.core.config import AppConfig

        strategy_params = (
            config.strategy_params if isinstance(config, AppConfig) else config.get("strategy_params", {})
        ) or {}
        cfg = {**self.DEFAULT_CONFIG, **strategy_params}
        self.strategy_cfg = merge_config(RsiNoRetestConfig, cfg)
        bot_cfg = config.get("bot", {}) if not isinstance(config, AppConfig) else {}

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

        risk_cfg = (
            config.get("risk", {})
            if not hasattr(config, "get") or isinstance(config, dict)
            else getattr(config, "risk", {})
        )
        if not isinstance(risk_cfg, dict):
            risk_cfg = risk_cfg.dict() if hasattr(risk_cfg, "dict") else {}

        self.taker_fee = Decimal(str(risk_cfg.get("taker_fee", DEFAULT_TAKER_FEE_DECIMAL)))
        self.maker_fee = Decimal(str(risk_cfg.get("maker_fee", DEFAULT_MAKER_FEE_DECIMAL)))

        # Strategy parameters
        self.lookback = int(cfg.get("nr_lookback", 30))
        self.max_above_ema21 = int(cfg.get("nr_max_above_ema21", 1))
        self.rsi_spread_min = float(cfg.get("nr_rsi_spread_min", 1.5))
        self.sl_mode = str(cfg.get("nr_sl_mode", "rsi_ema9")).lower()
        self.sl_buffer_pct = float(cfg.get("sl_buffer_pct", 0.0))
        self.disaster_sl_multiplier = float(cfg.get("disaster_sl_multiplier", 2.0))
        sl_trigger_mode = str(cfg.get("sl_trigger_mode", SL_TRIGGER_CANDLE_CLOSE)).lower()
        if sl_trigger_mode not in SL_TRIGGER_MODES:
            raise ValueError(
                f"sl_trigger_mode must be one of {SL_TRIGGER_MODES}, got {sl_trigger_mode!r}"
            )
        self.sl_trigger_mode = sl_trigger_mode
        self.candle_close_slippage_pct = float(cfg.get("candle_close_slippage_pct", 0.001))

        self.tp1_rr = Decimal(str(cfg.get("nr_tp1_rr", 1.0)))
        self.tp2_rr = Decimal(str(cfg.get("nr_tp2_rr", 2.0)))
        self.tp3_rr = Decimal(str(cfg.get("nr_tp3_rr", 3.0)))
        self.tp_count = int(cfg.get("nr_tp_count", 3))
        self.tp1_close_pct = float(cfg.get("tp1_close_pct", 0.5))
        self.tp2_close_pct = float(cfg.get("tp2_close_pct", 0.5))

        self.move_sl_rr = Decimal(str(cfg.get("nr_move_sl_rr", 0.5)))
        self.lock_profit_rr = Decimal(str(cfg.get("nr_lock_profit_rr", 0.2)))
        self.max_holding_enabled = bool(cfg.get("max_holding_enabled", True))
        self.max_holding_bars = int(cfg.get("max_holding_bars", 96) or 0)
        self.use_active_trades = bool(cfg.get("use_active_trades", True))

        self.debug_enabled = bool(bot_cfg.get("debug", False))
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

    def export_debug_csv(self, path: str) -> None:
        """Export per-candle debug rows collected during backtest to a CSV file."""
        if not self._debug_rows:
            return
        import os

        os.makedirs(os.path.dirname(path), exist_ok=True)
        pd.DataFrame(self._debug_rows).to_csv(path, index=False)

    # ---------------- main ----------------
    def analyze(
        self,
        symbol: str,
        df,
        position: PositionSnapshot | None = None,
        context: ContextSnapshot | None = None,
    ) -> AnalysisResult:
        if context is None:
            context = ContextSnapshot(state=SCANNING)

        _noop = AnalysisResult(actions=[DoNothing()], new_context=context)

        if df is None or len(df) < max(WARMUP, self.lookback + 10):
            return _noop

        if "closed" in df.columns and not bool(df.iloc[-1]["closed"]):
            return _noop

        df_tf = resample_dataframe(df, self.timeframe) if "timestamp" in getattr(df, "columns", []) else df
        df_ind = self.indicators.compute(df_tf, symbol=symbol, timeframe=self.timeframe)
        last = Indicators.last(df_ind)
        if not last:
            return _noop

        close = to_decimal_or_none(last.get("close"))
        high = to_decimal_or_none(last.get("high"))
        open_price = to_decimal_or_none(last.get("open"))
        ema21 = to_decimal_or_none(last.get("ema21"))

        if close is None or ema21 is None:
            return _noop

        rsi_ema9 = last.get("rsi_ema9")
        rsi_wma45 = last.get("rsi_wma45")

        # ---- EXIT / MANAGEMENT (position is open) ----
        if self.use_active_trades and position and position.has_position:
            return manage_exit(
                symbol=symbol,
                context=context,
                close=close,
                high=high,
                open_price=open_price,
                move_sl_rr=self.move_sl_rr,
                lock_profit_rr=self.lock_profit_rr,
                taker_fee=self.taker_fee,
                maker_fee=self.maker_fee,
                sl_trigger_mode=self.sl_trigger_mode,
                max_holding_bars=(
                    self.max_holding_bars if self.max_holding_enabled else 0
                ),
            )

        # ---- ENTRY (no open position) ----
        if self.debug_enabled:
            logger.debug(f"[{symbol}] DEBUG: State={context.state}, OHLCV Size={len(df)}")

        return check_entry(
            symbol=symbol,
            df_ind=df_ind,
            context=context,
            close=close,
            ema21=ema21,
            rsi_ema9=rsi_ema9,
            rsi_wma45=rsi_wma45,
            lookback=self.lookback,
            max_above_ema21=self.max_above_ema21,
            rsi_spread_min=self.rsi_spread_min,
            sl_mode=self.sl_mode,
            sl_buffer_pct=self.sl_buffer_pct,
            disaster_sl_multiplier=self.disaster_sl_multiplier,
            sl_trigger_mode=self.sl_trigger_mode,
            tp1_rr=self.tp1_rr,
            tp2_rr=self.tp2_rr,
            tp3_rr=self.tp3_rr,
            tp_count=self.tp_count,
            tp1_close_pct=self.tp1_close_pct,
            tp2_close_pct=self.tp2_close_pct,
            move_sl_rr=self.move_sl_rr,
            lock_profit_rr=self.lock_profit_rr,
            taker_fee=self.taker_fee,
            maker_fee=self.maker_fee,
            indicators=self.indicators,
            debug_enabled=self.debug_enabled,
            debug_rows=self._debug_rows,
            df_ind_index_last=df_ind.index[-1] if len(df_ind) >= 1 else None,
        )

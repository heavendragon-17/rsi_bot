"""
RsiAlertStrategy — alert-only (no trading).

Continuously monitors RSI14 on the configured timeframe (default M15) and
emits a Telegram alert when the live RSI (including the in-progress candle)
drops to a configured oversold threshold.

Two tiers are tracked independently:
  - warning_threshold (default 8.5)
  - strong_threshold  (default 8.0)

Each tier has its own per-symbol cooldown. After alerting on a tier, that
tier is muted for `cooldown_minutes` (default 120 = 2h) before it can fire
again on the same symbol.

The strategy returns SendAlert actions only — never OpenPosition. It sets
`tick_mode = True` so the runner evaluates it on every loop tick using the
full DataFrame (forming candle included) rather than only on candle close.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from dataclasses import fields as dc_fields

import pandas as pd
import structlog

from app.core.actions import DoNothing, SendAlert
from app.core.analysis_result import AnalysisResult
from app.core.snapshots import ContextSnapshot, PositionSnapshot
from app.data.indicators import Indicators
from app.trading.strategy.base import BaseStrategy
from app.trading.strategy.utils.config_helpers import merge_config

logger = structlog.get_logger()


@dataclass(frozen=True)
class RsiAlertConfig:
    """Typed config for RsiAlertStrategy."""

    rsi_period: int = 14
    warning_threshold: float = 8.5
    strong_threshold: float = 8.0
    cooldown_minutes: int = 120  # 2 hours
    min_candles: int = 30  # Warm-up: 14 RSI + buffer


class RsiAlertStrategy(BaseStrategy):
    """Alert-only strategy that fires when RSI14 reaches oversold tiers."""

    CONFIG_CLASS = RsiAlertConfig
    DEFAULT_CONFIG = {f.name: f.default for f in dc_fields(RsiAlertConfig)}

    # Runner hint: evaluate on every tick (using the in-progress candle),
    # not only when a candle closes.
    tick_mode = True

    def __init__(self, config: dict):
        super().__init__(config)
        self.cfg = merge_config(RsiAlertConfig, config) if config else RsiAlertConfig()
        if self.cfg.strong_threshold > self.cfg.warning_threshold:
            raise ValueError(
                "strong_threshold must be <= warning_threshold "
                f"(got strong={self.cfg.strong_threshold}, "
                f"warning={self.cfg.warning_threshold})"
            )
        self.indicators = Indicators(rsi_period=self.cfg.rsi_period)

    def analyze(
        self,
        symbol: str,
        df: pd.DataFrame,
        position: PositionSnapshot | None = None,
        context: ContextSnapshot | None = None,
    ) -> AnalysisResult:
        if context is None:
            context = ContextSnapshot()

        # Carry forward existing cooldown timestamps.
        meta = dict(context.meta or {})
        new_ctx = ContextSnapshot(
            state=context.state,
            soft_sl_price=context.soft_sl_price,
            meta=meta,
        )
        noop = AnalysisResult(actions=[DoNothing()], new_context=new_ctx)

        if df is None or len(df) < self.cfg.min_candles:
            return noop

        df_ind = self.indicators.compute(df)
        rsi_series = df_ind.get("rsi_14")
        if rsi_series is None or rsi_series.empty:
            return noop

        current_rsi = rsi_series.iloc[-1]
        if pd.isna(current_rsi):
            return noop

        rsi_val = float(current_rsi)
        now = time.time()
        cooldown_s = self.cfg.cooldown_minutes * 60

        # Pick the deepest tier that is currently breached AND off cooldown.
        # "Strong" wins over "warning" if both are breached and both ready.
        if rsi_val <= self.cfg.strong_threshold:
            tier = "strong"
            threshold = self.cfg.strong_threshold
        elif rsi_val <= self.cfg.warning_threshold:
            tier = "warning"
            threshold = self.cfg.warning_threshold
        else:
            return noop

        last_key = f"rsi_alert_last_{tier}_ts"
        last_ts = float(meta.get(last_key, 0.0) or 0.0)
        if now - last_ts < cooldown_s:
            return noop

        meta[last_key] = now
        label = "STRONG" if tier == "strong" else "WARNING"
        message = (
            f"🚨 RSI {label} | {symbol}\n"
            f"RSI14 = {rsi_val:.2f} (≤ {threshold})\n"
            f"Cooldown: {self.cfg.cooldown_minutes} min"
        )
        logger.info(
            "rsi_alert.fired",
            symbol=symbol,
            tier=tier,
            rsi=rsi_val,
            threshold=threshold,
        )
        return AnalysisResult(
            actions=[SendAlert(symbol=symbol, message=message, tier=tier)],
            new_context=ContextSnapshot(
                state=new_ctx.state,
                soft_sl_price=new_ctx.soft_sl_price,
                meta=meta,
            ),
        )

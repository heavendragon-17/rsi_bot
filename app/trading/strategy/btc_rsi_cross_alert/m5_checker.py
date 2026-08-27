"""Pure 5-minute candle checker for the BTC RSI cross alert.

This module is the M5-specific entry point. Shared RSI preparation and signal
math remain in :mod:`evaluator` so the M5 and M15 implementations cannot drift.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

import pandas as pd

from app.trading.strategy.btc_rsi_cross_alert.evaluator import (
    prepare_btc_rsi_cross_input,
)
from app.trading.strategy.btc_rsi_cross_alert.models import (
    DECISION_ALERT_M5_BULLISH_ALIGNMENT_H4_BULLISH,
    DECISION_H4_CLOSE_NOT_ABOVE_EMA21,
    DECISION_M5_CLOSE_NOT_ABOVE_EMA21,
    DECISION_M5_EMA_WMA_SPREAD_NOT_ABOVE_2,
    DECISION_M5_RSI_ALIGNMENT_NOT_BULLISH,
    DECISION_M5_WMA45_NOT_ABOVE_45,
    BtcRsiCrossDecision,
    BtcRsiCrossInput,
    BtcRsiCrossPreparation,
    build_event_id,
)

M5_TIMEFRAME: Final[str] = "5m"
M5_MIN_RSI_EMA_WMA_SPREAD: Final[float] = 2.0
M5_MIN_RSI_WMA45: Final[float] = 45.0


def prepare_m5_cross_input(
    trigger_df: pd.DataFrame,
    h4_df: pd.DataFrame,
    *,
    symbol: str,
    trigger_open_time: datetime,
    history_ready_at: datetime,
    observed_live_h4_closes: frozenset[datetime],
) -> BtcRsiCrossPreparation:
    """Prepare one closed M5 candle against its exact eligible H4 context."""

    return prepare_btc_rsi_cross_input(
        trigger_df,
        h4_df,
        symbol=symbol,
        trigger_timeframe=M5_TIMEFRAME,
        trigger_open_time=trigger_open_time,
        history_ready_at=history_ready_at,
        observed_live_h4_closes=observed_live_h4_closes,
    )


def evaluate_m5_cross(data: BtcRsiCrossInput) -> BtcRsiCrossDecision:
    """Evaluate a prepared M5 input and reject accidental cross-timeframe use."""

    if data.trigger_timeframe != M5_TIMEFRAME:
        raise ValueError(
            f"M5 checker requires trigger_timeframe={M5_TIMEFRAME!r}, "
            f"got {data.trigger_timeframe!r}"
        )
    event_id = build_event_id(
        symbol=data.symbol,
        trigger_timeframe=data.trigger_timeframe,
        trigger_close_time=data.trigger_close_time,
    )

    m5_bullish_alignment = (
        data.current_trigger.rsi21 > data.current_trigger.rsi_ema9
        and data.current_trigger.rsi_ema9 > data.current_trigger.rsi_wma45
    )
    if not m5_bullish_alignment:
        return BtcRsiCrossDecision(
            should_alert=False,
            event_id=event_id,
            reason=DECISION_M5_RSI_ALIGNMENT_NOT_BULLISH,
        )

    if data.h4_close_price <= data.h4_price_ema21:
        return BtcRsiCrossDecision(
            should_alert=False,
            event_id=event_id,
            reason=DECISION_H4_CLOSE_NOT_ABOVE_EMA21,
        )

    rsi_spread = data.current_trigger.rsi_ema9 - data.current_trigger.rsi_wma45
    if rsi_spread <= M5_MIN_RSI_EMA_WMA_SPREAD:
        return BtcRsiCrossDecision(
            should_alert=False,
            event_id=event_id,
            reason=DECISION_M5_EMA_WMA_SPREAD_NOT_ABOVE_2,
        )

    if data.current_trigger.rsi_wma45 <= M5_MIN_RSI_WMA45:
        return BtcRsiCrossDecision(
            should_alert=False,
            event_id=event_id,
            reason=DECISION_M5_WMA45_NOT_ABOVE_45,
        )

    if data.trigger_close_price <= data.trigger_price_ema21:
        return BtcRsiCrossDecision(
            should_alert=False,
            event_id=event_id,
            reason=DECISION_M5_CLOSE_NOT_ABOVE_EMA21,
        )

    return BtcRsiCrossDecision(
        should_alert=True,
        event_id=event_id,
        reason=DECISION_ALERT_M5_BULLISH_ALIGNMENT_H4_BULLISH,
    )

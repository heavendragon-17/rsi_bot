"""Pure 15-minute candle checker for the BTC RSI cross alert.

This module is the M15-specific entry point. Shared RSI preparation and signal
math remain in :mod:`evaluator` so the M5 and M15 implementations cannot drift.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

import pandas as pd

from app.trading.strategy.btc_rsi_cross_alert.evaluator import (
    evaluate_btc_rsi_cross,
    prepare_btc_rsi_cross_input,
)
from app.trading.strategy.btc_rsi_cross_alert.models import (
    DECISION_M15_CLOSE_NOT_ABOVE_EMA21,
    BtcRsiCrossDecision,
    BtcRsiCrossInput,
    BtcRsiCrossPreparation,
)

M15_TIMEFRAME: Final[str] = "15m"


def prepare_m15_cross_input(
    trigger_df: pd.DataFrame,
    h4_df: pd.DataFrame,
    *,
    symbol: str,
    trigger_open_time: datetime,
    history_ready_at: datetime,
    observed_live_h4_closes: frozenset[datetime],
) -> BtcRsiCrossPreparation:
    """Prepare one closed M15 candle against its exact eligible H4 context."""

    return prepare_btc_rsi_cross_input(
        trigger_df,
        h4_df,
        symbol=symbol,
        trigger_timeframe=M15_TIMEFRAME,
        trigger_open_time=trigger_open_time,
        history_ready_at=history_ready_at,
        observed_live_h4_closes=observed_live_h4_closes,
    )


def evaluate_m15_cross(data: BtcRsiCrossInput) -> BtcRsiCrossDecision:
    """Evaluate a prepared M15 input and reject accidental cross-timeframe use."""

    if data.trigger_timeframe != M15_TIMEFRAME:
        raise ValueError(
            f"M15 checker requires trigger_timeframe={M15_TIMEFRAME!r}, "
            f"got {data.trigger_timeframe!r}"
        )
    shared_decision = evaluate_btc_rsi_cross(data)
    if not shared_decision.should_alert:
        return shared_decision

    if data.trigger_close_price <= data.trigger_price_ema21:
        return BtcRsiCrossDecision(
            should_alert=False,
            event_id=shared_decision.event_id,
            reason=DECISION_M15_CLOSE_NOT_ABOVE_EMA21,
        )

    return shared_decision

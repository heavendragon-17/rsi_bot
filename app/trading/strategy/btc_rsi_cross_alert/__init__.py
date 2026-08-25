"""Pure domain layer for the BTC RSI cross alert.

Public exports of the frozen models, exact reason constants, deterministic
event identity, and the two pure functions. This package is deliberately NOT
registered in ``app.trading.strategy.loader`` — it does not implement the
single-frame ``IStrategy`` contract and must never appear in the backtest UI
or database seed.
"""

from app.trading.strategy.btc_rsi_cross_alert.evaluator import (
    RETRYABLE_PREPARATION_REASONS,
    RSI_BUNDLE_MINIMUM_ROWS,
    TRIGGER_MINIMUM_ROWS,
    candle_close_time,
    evaluate_btc_rsi_cross,
    expected_h4_close_for,
    normalize_candle_open,
    prepare_btc_rsi_cross_input,
)
from app.trading.strategy.btc_rsi_cross_alert.models import (
    COMPONENT_NAME,
    DECISION_ALERT_FRESH_BULLISH_CROSS_H4_BULLISH,
    DECISION_H4_NOT_BULLISH,
    DECISION_NO_FRESH_BULLISH_CROSS,
    DECISION_REASONS,
    EVENT_ID_PREFIX,
    EVENT_ID_SUFFIX_LENGTH,
    H4_DUPLICATE_OR_NON_INCREASING_TIME,
    H4_EXPECTED_CLOSE_MISSING,
    H4_INSUFFICIENT_CONTIGUOUS_HISTORY,
    H4_LIVE_CLOSE_UNCONFIRMED,
    H4_NON_FINITE_DATA,
    PREPARATION_READY,
    PREPARATION_REASONS,
    TRIGGER_CURRENT_ROW_MISSING,
    TRIGGER_DUPLICATE_OR_NON_INCREASING_TIME,
    TRIGGER_INSUFFICIENT_CONTIGUOUS_HISTORY,
    TRIGGER_NON_FINITE_DATA,
    TRIGGER_UNSUPPORTED_TIMEFRAME,
    BtcRsiCrossDecision,
    BtcRsiCrossInput,
    BtcRsiCrossPreparation,
    RsiBundlePoint,
    build_event_id,
    event_id_suffix,
)

__all__ = [
    "COMPONENT_NAME",
    "DECISION_ALERT_FRESH_BULLISH_CROSS_H4_BULLISH",
    "DECISION_H4_NOT_BULLISH",
    "DECISION_NO_FRESH_BULLISH_CROSS",
    "DECISION_REASONS",
    "EVENT_ID_PREFIX",
    "EVENT_ID_SUFFIX_LENGTH",
    "H4_DUPLICATE_OR_NON_INCREASING_TIME",
    "H4_EXPECTED_CLOSE_MISSING",
    "H4_INSUFFICIENT_CONTIGUOUS_HISTORY",
    "H4_LIVE_CLOSE_UNCONFIRMED",
    "H4_NON_FINITE_DATA",
    "PREPARATION_READY",
    "PREPARATION_REASONS",
    "RETRYABLE_PREPARATION_REASONS",
    "RSI_BUNDLE_MINIMUM_ROWS",
    "TRIGGER_MINIMUM_ROWS",
    "TRIGGER_CURRENT_ROW_MISSING",
    "TRIGGER_DUPLICATE_OR_NON_INCREASING_TIME",
    "TRIGGER_INSUFFICIENT_CONTIGUOUS_HISTORY",
    "TRIGGER_NON_FINITE_DATA",
    "TRIGGER_UNSUPPORTED_TIMEFRAME",
    "BtcRsiCrossDecision",
    "BtcRsiCrossInput",
    "BtcRsiCrossPreparation",
    "RsiBundlePoint",
    "build_event_id",
    "candle_close_time",
    "evaluate_btc_rsi_cross",
    "event_id_suffix",
    "expected_h4_close_for",
    "normalize_candle_open",
    "prepare_btc_rsi_cross_input",
]

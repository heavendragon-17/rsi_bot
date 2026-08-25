"""Runtime and configuration components for the BTC RSI cross alert.

The worker here is orchestrated by the existing ``SignalRunner``; it never
places orders, creates virtual positions, or touches the mechanical exit
monitor. This component is not registered in the trading/backtest strategy
loader.
"""

from app.signal.btc_rsi_cross_alert.config import (
    CANONICAL_SYMBOL,
    COMPONENT_NAME,
    LOCKED_RSI_EMA_PERIOD,
    LOCKED_RSI_PERIOD,
    LOCKED_RSI_WMA_PERIOD,
    LOCKED_TREND_TIMEFRAME,
    LOCKED_TRIGGER_TIMEFRAMES,
    MAX_CONTEXT_SETTLE_SECONDS,
    MIN_CONTEXT_SETTLE_SECONDS,
    BtcRsiCrossAlertConfig,
    is_btc_rsi_cross_alert_entry,
    resolve_btc_rsi_cross_alert_config,
)
from app.signal.btc_rsi_cross_alert.formatter import format_btc_rsi_cross_alert
from app.signal.btc_rsi_cross_alert.worker import BtcRsiCrossAlertWorker

__all__ = [
    "CANONICAL_SYMBOL",
    "COMPONENT_NAME",
    "LOCKED_RSI_EMA_PERIOD",
    "LOCKED_RSI_PERIOD",
    "LOCKED_RSI_WMA_PERIOD",
    "LOCKED_TRIGGER_TIMEFRAMES",
    "LOCKED_TREND_TIMEFRAME",
    "MAX_CONTEXT_SETTLE_SECONDS",
    "MIN_CONTEXT_SETTLE_SECONDS",
    "BtcRsiCrossAlertConfig",
    "BtcRsiCrossAlertWorker",
    "format_btc_rsi_cross_alert",
    "is_btc_rsi_cross_alert_entry",
    "resolve_btc_rsi_cross_alert_config",
]

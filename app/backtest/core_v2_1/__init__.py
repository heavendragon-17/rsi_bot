"""Point-in-time replay and market-data tooling for Core V2.1.

This package is deliberately separate from the generic trade-execution
backtester.  Core V2.1 is a signal state machine with several synchronized
timeframes, so its replay needs an explicit as-of data contract.
"""

from app.backtest.core_v2_1.data import (
    AsOfRow,
    CandleDataError,
    CandleValidationReport,
    PointInTimeContext,
    build_point_in_time_context,
    load_stored_candles,
    resample_closed_candles,
)

__all__ = [
    "AsOfRow",
    "CandleDataError",
    "CandleValidationReport",
    "PointInTimeContext",
    "build_point_in_time_context",
    "load_stored_candles",
    "resample_closed_candles",
]

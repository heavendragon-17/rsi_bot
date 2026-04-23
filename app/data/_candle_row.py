"""Shared helpers for building candle rows and reading them back.

Used by :class:`app.data.store.MarketDataStore` (single-TF live bot path) and
:class:`app.data.multiplexer.TimeframeMultiplexer` (multi-TF signal-bot path)
so the dual float/Decimal column contract lives in one place.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pandas as pd

from app.core.events import Candle


def candle_to_row(candle: Candle) -> dict[str, Any]:
    """Build the DataFrame row dict used by the candle stores.

    Float columns drive pandas operations; ``_dec`` columns preserve
    Decimal precision for financial calculations.
    """
    return {
        "timestamp": candle.timestamp,
        "open": float(candle.open),
        "high": float(candle.high),
        "low": float(candle.low),
        "close": float(candle.close),
        "volume": float(candle.volume),
        "closed": candle.closed,
        "open_dec": candle.open,
        "high_dec": candle.high,
        "low_dec": candle.low,
        "close_dec": candle.close,
    }


def last_row_to_decimal_dict(df: pd.DataFrame | None) -> dict | None:
    """Return the last row of ``df`` as a Decimal-typed dict, or ``None``."""
    if df is None or df.empty:
        return None

    row = df.iloc[-1]
    return {
        "timestamp": row.name,
        "open": row.get("open_dec", Decimal(str(row["open"]))),
        "high": row.get("high_dec", Decimal(str(row["high"]))),
        "low": row.get("low_dec", Decimal(str(row["low"]))),
        "close": row.get("close_dec", Decimal(str(row["close"]))),
        "volume": Decimal(str(row["volume"])),
        "closed": row["closed"],
    }

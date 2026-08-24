"""Restart-safe, signal-only runtime support for Core V2.1.

This package is deliberately separate from :mod:`app.signal.runner`.  Core
V2.1 consumes several venues and timeframes, whereas the legacy signal runner
is a Binance-only, single-strategy-frame pipeline.  Nothing in this package
places orders.
"""

from app.signal.core_v2_1.models import (
    AdvisoryEvent,
    AdvisoryEventType,
    AsOfBundle,
    BundleRequirement,
    ClosedCandle,
    MarketKey,
    MarketPlan,
    MarketSeries,
    TriggerPlan,
    Venue,
)

__all__ = [
    "AdvisoryEvent",
    "AdvisoryEventType",
    "AsOfBundle",
    "BundleRequirement",
    "ClosedCandle",
    "MarketKey",
    "MarketPlan",
    "MarketSeries",
    "TriggerPlan",
    "Venue",
]

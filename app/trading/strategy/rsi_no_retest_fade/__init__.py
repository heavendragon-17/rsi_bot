"""RSI No Retest FADE strategy package.

Same trigger as ``rsi_no_retest`` (the LONG parent) but emits SELL instead
of BUY — i.e. it FADES the parent's entries rather than mirroring them
with a break-down trigger like ``rsi_no_retest_short`` does.

Hypothesis: if the parent's reclaim trigger has negative IC at h=4, then
betting against it (same trigger, opposite direction) preserves more
signal than rebuilding a mirror trigger from scratch (which loses signal
to the unrelated noise of the bearish-spread filter).

Re-exports the strategy class and config so callers can import via
``from app.trading.strategy.rsi_no_retest_fade import RsiNoRetestFadeStrategy``.
"""

from app.trading.strategy.rsi_no_retest_fade.strategy import (
    RsiNoRetestFadeConfig,
    RsiNoRetestFadeStrategy,
)

__all__ = ["RsiNoRetestFadeConfig", "RsiNoRetestFadeStrategy"]

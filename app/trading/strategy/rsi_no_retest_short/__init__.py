"""RSI No Retest SHORT strategy package.

H3 contrarian variant of ``rsi_no_retest`` motivated by the audit's
Information Coefficient finding (negative IC at h=4 across the trading
universe). Pure inversion: same parameters, same triggers, opposite
direction.

Re-exports the strategy class and config so callers can import via
``from app.trading.strategy.rsi_no_retest_short import RsiNoRetestShortStrategy``.
"""

from app.trading.strategy.rsi_no_retest_short.strategy import (
    RsiNoRetestShortConfig,
    RsiNoRetestShortStrategy,
)

__all__ = ["RsiNoRetestShortConfig", "RsiNoRetestShortStrategy"]

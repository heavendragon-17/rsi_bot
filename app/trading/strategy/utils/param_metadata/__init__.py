"""UI metadata for strategy parameter schemas.

Re-exports per-strategy metadata dicts so existing imports
(``from app.trading.strategy.utils.param_metadata import ...``)
keep working after the file was split into a package.
"""

from app.trading.strategy.utils.param_metadata._groups import INDICATOR_GROUPS
from app.trading.strategy.utils.param_metadata._momentum import (
    RSI_MOMENTUM_GROUPS,
    RSI_MOMENTUM_METADATA,
)
from app.trading.strategy.utils.param_metadata._no_retest import (
    RSI_NO_RETEST_FADE_GROUPS,
    RSI_NO_RETEST_FADE_METADATA,
    RSI_NO_RETEST_GROUPS,
    RSI_NO_RETEST_METADATA,
    RSI_NO_RETEST_SHORT_GROUPS,
    RSI_NO_RETEST_SHORT_METADATA,
)
from app.trading.strategy.utils.param_metadata._wma_retest import (
    RSI_WMA_RETEST_GROUPS,
    RSI_WMA_RETEST_METADATA,
)

__all__ = [
    "INDICATOR_GROUPS",
    "RSI_MOMENTUM_GROUPS",
    "RSI_MOMENTUM_METADATA",
    "RSI_NO_RETEST_FADE_GROUPS",
    "RSI_NO_RETEST_FADE_METADATA",
    "RSI_NO_RETEST_GROUPS",
    "RSI_NO_RETEST_METADATA",
    "RSI_NO_RETEST_SHORT_GROUPS",
    "RSI_NO_RETEST_SHORT_METADATA",
    "RSI_WMA_RETEST_GROUPS",
    "RSI_WMA_RETEST_METADATA",
]

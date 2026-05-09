"""RSI Momentum (short) strategy package.

Re-exports the strategy class so existing import sites
(`from app.trading.strategy.rsi_momentum import RsiMomentumStrategy`)
continue to work after the file-to-folder refactor.
"""

from app.trading.strategy.rsi_momentum.strategy import (
    RsiMomentumConfig,
    RsiMomentumStrategy,
)

__all__ = ["RsiMomentumConfig", "RsiMomentumStrategy"]

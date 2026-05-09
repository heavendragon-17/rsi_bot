# app/strategies/loader.py
"""
Strategy Loader
===============
Dynamic strategy loading based on configuration.
"""

from app.core.interfaces import IStrategy

from .rsi_momentum import RsiMomentumStrategy
from .rsi_no_retest import RsiNoRetestStrategy
from .rsi_no_retest_fade import RsiNoRetestFadeStrategy
from .rsi_no_retest_short import RsiNoRetestShortStrategy
from .rsi_wma_retest import RsiWmaRetestStrategy

# Strategy name -> class mapping
STRATEGY_MAP = {
    "rsi_wma_retest": RsiWmaRetestStrategy,
    "rsi_no_retest": RsiNoRetestStrategy,
    "rsi_no_retest_short": RsiNoRetestShortStrategy,
    "rsi_no_retest_fade": RsiNoRetestFadeStrategy,
    "rsi_momentum": RsiMomentumStrategy,
}


def get_available_strategies() -> list:
    """Return list of available strategy names."""
    return list(STRATEGY_MAP.keys())


def load_strategy(config: dict) -> type[IStrategy]:
    """
    Load strategy CLASS based on config['strategy'].

    Args:
        config: Application configuration dict

    Returns:
        Strategy class (not instance)

    Raises:
        ValueError: If strategy name is unknown
    """
    name = config.get("strategy", "rsi_wma_retest")

    if name not in STRATEGY_MAP:
        available = ", ".join(STRATEGY_MAP.keys())
        raise ValueError(f"Unknown strategy: '{name}'. Available: {available}")

    return STRATEGY_MAP[name]


def load_strategy_instance(config: dict) -> IStrategy:
    """
    Load and instantiate a strategy based on config['strategy'].

    Args:
        config: Application configuration dict

    Returns:
        Instantiated strategy object
    """
    strategy_class = load_strategy(config)
    return strategy_class(config)

"""
Base Strategy
==============
Base class for all trading strategies.
"""
from abc import abstractmethod
from app.core.interfaces import IStrategy
from app.core.context import StrategyContext


class BaseStrategy(IStrategy):
    """Base class for all trading strategies with context management."""
    
    def __init__(self, config: dict):
        self.config = config
        self.context = StrategyContext()

    @abstractmethod
    def analyze(self, symbol: str, df):
        """Analyze market data and return signal if conditions are met."""
        pass

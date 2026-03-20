"""
Base Strategy
==============
Base class for all trading strategies.
"""
from abc import abstractmethod
from typing import Optional

from app.core.interfaces import IStrategy
from app.core.context import StrategyContext
from app.core.snapshots import PositionSnapshot, ContextSnapshot
from app.core.analysis_result import AnalysisResult


class BaseStrategy(IStrategy):
    """Base class for all trading strategies."""

    def __init__(self, config: dict):
        self.config = config
        # Kept for backward compatibility with tests that inject state directly.
        # New stateless analyze() does not mutate or read self.context.
        self.context = StrategyContext()

    @abstractmethod
    def analyze(
        self,
        symbol: str,
        df,
        position: Optional[PositionSnapshot] = None,
        context: Optional[ContextSnapshot] = None,
    ) -> AnalysisResult:
        """Analyze market data and return typed actions + new context."""
        pass

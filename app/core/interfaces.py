from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Sequence
import pandas as pd


class IExchange(ABC):
    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> Sequence[Sequence[Any]]:
        """
        Fetch historical OHLCV candles.

        Typical return format (like CCXT):
            [
                [timestamp_ms, open, high, low, close, volume],
                ...
            ]
        """
        pass

    @abstractmethod
    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Executes an order.

        Args:
            symbol: e.g. "BTC/USDT"
            order_type: e.g. "market" or "limit"
            side: e.g. "buy" or "sell"
            amount: position size
            price: required for limit orders

        Returns:
            Order details (dict) on success, None on failure.
        """
        pass

    @abstractmethod
    def get_balance(self) -> float:
        """
        Returns the total balance in quote currency (e.g. USDT).
        """
        pass


class IStrategy(ABC):
    @abstractmethod
    def analyze(self, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
        """
        Analyze the latest market data and return a signal dict, or None.

        Return example:
            {"type": "ALERT", "symbol": "BTC/USDT", "reason": "..."}
        """
        pass


class IDataProvider(ABC):
    @abstractmethod
    def subscribe(self, symbols: List[str]) -> None:
        """
        Subscribe to live streams for the provided symbols.
        """
        pass

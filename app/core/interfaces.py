"""
Clean Architecture Interfaces
Layer 1: Data Ingestion  - IDataProvider, IDataStore
Layer 2: Core Logic      - IStrategy, IIndicators  
Layer 3: Execution       - IExchange, IPortfolio
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional, Dict, Any, List, Sequence
import pandas as pd

from app.core.events import Candle, SignalEvent, MarketEvent
from app.core.snapshots import PositionSnapshot, ContextSnapshot
from app.core.analysis_result import AnalysisResult


# ============================================
# Layer 1: Data Ingestion Interfaces
# ============================================

class IDataProvider(ABC):
    """Interface for market data providers (websocket streams, REST APIs)."""
    
    @abstractmethod
    def subscribe(self, symbols: List[str]) -> None:
        """Subscribe to market data for given symbols."""
        pass
    
    @abstractmethod
    def unsubscribe(self, symbols: List[str]) -> None:
        """Unsubscribe from market data."""
        pass


class IDataStore(ABC):
    """Interface for storing and retrieving candle data."""
    
    @abstractmethod
    def update_candle(self, candle: Candle) -> None:
        """Update or append candle data."""
        pass
    
    @abstractmethod
    def get_dataframe(self, symbol: str) -> Optional[pd.DataFrame]:
        """Get candle data as DataFrame for a symbol."""
        pass


# ============================================
# Layer 2: Core Logic Interfaces
# ============================================

class IIndicators(ABC):
    """Interface for technical indicator calculations."""
    
    @abstractmethod
    def compute(self, df: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Compute all indicators and return DataFrame with new columns."""
        pass
    
    @abstractmethod
    def get_mode(self, df: pd.DataFrame) -> str:
        """Get current market mode (BULLISH, NEUTRAL)."""
        pass
    
    @abstractmethod
    def check_wma_retest(self, df: pd.DataFrame, distance: float) -> bool:
        """Check if RSI is retesting WMA45 within distance."""
        pass
    
    @abstractmethod
    def calculate_price_at_rsi(self, df: pd.DataFrame, target_rsi: float) -> Decimal:
        """Calculate the price level for a target RSI value."""
        pass


class IStrategy(ABC):
    """Interface for trading strategies."""

    @abstractmethod
    def analyze(
        self,
        symbol: str,
        df: pd.DataFrame,
        position: Optional[PositionSnapshot] = None,
        context: Optional[ContextSnapshot] = None,
    ) -> AnalysisResult:
        """
        Pure analysis function.

        Args:
            symbol:   Trading pair.
            df:       OHLCV DataFrame with pre-computed indicators.
            position: Current position state from Portfolio (None = no position).
            context:  Strategy state machine snapshot (None = start fresh).

        Returns:
            AnalysisResult with typed actions and the new context to store.
        """
        pass


# ============================================
# Layer 3: Execution Interfaces
# ============================================

class IExchange(ABC):
    """Interface for exchange operations."""
    
    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> Sequence[Sequence[Any]]:
        """
        Fetch historical OHLCV candles.
        Returns: [[timestamp_ms, open, high, low, close, volume], ...]
        """
        pass

    @abstractmethod
    def create_order(
        self,
        symbol: str,
        order_type: str,  # normalized: market, limit, stop_market, stop_limit, trailing_stop
        side: str,
        amount: Decimal,
        price: Optional[Decimal] = None,
        params: Optional[Dict[str, Any]] = None,  # stopPrice, reduceOnly, callbackRate, etc.
    ) -> Optional[Dict[str, Any]]:
        """
        Create an order using normalized order types.
        Adapter translates to exchange-native format.
        Returns order details (dict) on success, None on failure.
        """
        pass

    @abstractmethod
    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Fetch order status by ID."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an open order."""
        pass


class IFuturesExchange(IExchange):
    """Interface for perpetual futures exchange operations."""
    
    @abstractmethod
    def set_leverage(self, leverage: int, symbol: str) -> bool:
        """Set leverage for a symbol."""
        pass
    
    @abstractmethod
    def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict]:
        """Fetch open positions."""
        pass
    
    @abstractmethod
    def fetch_balance(self, params: Optional[Dict] = None) -> Dict:
        """Fetch balance in CCXT format."""
        pass

    @abstractmethod
    def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch all open/pending orders for a symbol."""
        pass

    @abstractmethod
    def cancel_all_orders(self, symbol: str) -> int:
        """Cancel all open orders for a symbol. Returns count cancelled."""
        pass


class IPortfolio(ABC):
    """Interface for portfolio management."""
    
    @abstractmethod
    def on_signal(self, signal: SignalEvent) -> None:
        """Process a trading signal."""
        pass
    
    @abstractmethod
    def has_position(self, symbol: str) -> bool:
        """Check if there's an open position for symbol."""
        pass
    
    @abstractmethod
    def close_position(self, symbol: str, percentage: Decimal) -> None:
        """Close percentage of position (0.0 - 1.0)."""
        pass

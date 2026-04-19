"""
Clean Architecture Interfaces
Layer 1: Data Ingestion  - IDataProvider, IDataStore
Layer 2: Core Logic      - IStrategy, IIndicators
Layer 3: Execution       - IExchange (unified futures exchange), IPortfolio
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from decimal import Decimal
from typing import Any

import pandas as pd

from app.core.analysis_result import AnalysisResult
from app.core.events import Candle, SignalEvent
from app.core.snapshots import ContextSnapshot, PositionSnapshot

# ============================================
# Layer 1: Data Ingestion Interfaces
# ============================================


class IDataProvider(ABC):
    """Interface for market data providers (websocket streams, REST APIs)."""

    @abstractmethod
    def subscribe(self, symbols: list[str]) -> None:
        """Subscribe to market data for given symbols."""
        pass

    @abstractmethod
    def unsubscribe(self, symbols: list[str]) -> None:
        """Unsubscribe from market data."""
        pass


class IDataStore(ABC):
    """Interface for storing and retrieving candle data."""

    @abstractmethod
    def update_candle(self, candle: Candle) -> None:
        """Update or append candle data."""
        pass

    @abstractmethod
    def get_dataframe(self, symbol: str) -> pd.DataFrame | None:
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
        position: PositionSnapshot | None = None,
        context: ContextSnapshot | None = None,
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
    """Interface for perpetual futures exchange operations."""

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
        price: Decimal | None = None,
        params: dict[str, Any] | None = None,  # stopPrice, reduceOnly, callbackRate, etc.
    ) -> dict[str, Any] | None:
        """
        Create an order using normalized order types.
        Adapter translates to exchange-native format.
        Returns order details (dict) on success, None on failure.
        """
        pass

    @abstractmethod
    def fetch_order(self, order_id: str, symbol: str) -> dict[str, Any]:
        """Fetch order status by ID."""
        pass

    @abstractmethod
    def cancel_order(self, order_id: str, symbol: str) -> bool:
        """Cancel an open order."""
        pass

    @abstractmethod
    def set_leverage(self, leverage: int, symbol: str) -> bool:
        """Set leverage for a symbol."""
        pass

    @abstractmethod
    def fetch_positions(self, symbols: list[str] | None = None) -> list[dict]:
        """Fetch open positions."""
        pass

    @abstractmethod
    def fetch_balance(self, params: dict | None = None) -> dict:
        """Fetch balance in CCXT format."""
        pass

    @abstractmethod
    def fetch_open_orders(self, symbol: str | None = None) -> list[dict[str, Any]]:
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


# ============================================
# Notification Interface
# ============================================


class INotifier(ABC):
    """
    Trade notification interface.

    All methods MUST be non-blocking and never raise — they are called from
    trading threads. Use scalar parameters only; no exchange-adapter-specific
    state objects are passed so this interface is decoupled from sim/live/paper.
    """

    @abstractmethod
    def send_message(self, message: str) -> None:
        """Send a plain-text (or HTML) message."""
        pass

    @abstractmethod
    def on_entry(
        self,
        symbol: str,
        side: str,
        entry_price: Decimal,
        amount: Decimal,
        sl_price: Decimal | None = None,
        tp_prices: dict[str, Decimal] | None = None,
        leverage: int = 1,
        balance: Decimal | None = None,
        indicators: dict[str, float] | None = None,
        entry_fee: Decimal | None = None,
        reason: str | None = None,
        soft_sl_price: Decimal | None = None,
        lock_profit_price: Decimal | None = None,
        tp_allocations: dict[str, float] | None = None,
        signal_class: int | None = None,
        risk_per_trade_pct: Decimal | None = None,
    ) -> None:
        """Called when a position is opened (entry order filled)."""
        pass

    @abstractmethod
    def on_fill(
        self,
        symbol: str,
        exit_reason: str,
        fill_price: Decimal,
        amount: Decimal,
        pnl_gross: Decimal | None = None,
        pnl_net: Decimal | None = None,
        fees: Decimal | None = None,
        r_multiple: Decimal | None = None,
        remaining_amount: Decimal | None = None,
        balance: Decimal | None = None,
        entry_price: Decimal | None = None,
        total_fees: Decimal | None = None,
        hold_duration: float | None = None,
        return_pct: Decimal | None = None,
    ) -> None:
        """Called when an SL or TP order fills (partial or full exit)."""
        pass

    @abstractmethod
    def on_error(self, context: str, error: str) -> None:
        """Called on a critical error (order rejection, exchange failure, etc.)."""
        pass

    @abstractmethod
    def on_funding(
        self,
        symbol: str,
        rate: Decimal,
        payment: Decimal,
        balance: Decimal,
    ) -> None:
        """Called every 8 hours when funding fees are deducted (sim mode)."""
        pass

    @abstractmethod
    def on_toggle(self, is_paused: bool) -> None:
        """Called when bot execution is paused or resumed."""
        pass

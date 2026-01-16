"""
Hyperliquid Adapter Stub
========================
Placeholder for future Hyperliquid perpetual futures integration.
Implements IFuturesExchange interface.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional, Dict, Any, List, Sequence

from app.core.interfaces import IFuturesExchange


class HyperliquidAdapter(IFuturesExchange):
    """
    Hyperliquid perpetual futures exchange adapter (STUB).
    
    NOTE: This is a placeholder for future implementation.
    All methods raise NotImplementedError.
    """
    
    def __init__(self, config: dict):
        self.config = config
        raise NotImplementedError("HyperliquidAdapter is not yet implemented")
    
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> Sequence[Sequence[Any]]:
        raise NotImplementedError

    def create_order(self, symbol: str, type: str, side: str, amount: float, price: Optional[float] = None, params: Dict = {}) -> Dict:
        raise NotImplementedError
    
    def fetch_balance(self, params: Dict = {}) -> Dict:
        raise NotImplementedError

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        raise NotImplementedError
    
    def set_leverage(self, symbol: str, leverage: int) -> None:
        raise NotImplementedError
    
    def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict]:
        raise NotImplementedError    


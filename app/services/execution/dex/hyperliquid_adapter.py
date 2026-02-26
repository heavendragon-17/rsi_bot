from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from app.core.interfaces import IExchange


class HyperliquidAdapter(IExchange):
    def __init__(self, config):
        self.config = config
        # SDK init here

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> Sequence[Sequence[Any]]:
        raise NotImplementedError

    def create_order(self, symbol: str, order_type: str, side: str, amount: Decimal,
                     price: Optional[Decimal] = None, params: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        raise NotImplementedError

    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        raise NotImplementedError

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        raise NotImplementedError

    def set_leverage(self, leverage: int, symbol: str) -> bool:
        raise NotImplementedError

    def fetch_positions(self, symbols: Optional[List[str]] = None) -> List[Dict]:
        raise NotImplementedError

    def fetch_balance(self, params: Optional[Dict] = None) -> Dict:
        raise NotImplementedError

    def fetch_open_orders(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        raise NotImplementedError

    def cancel_all_orders(self, symbol: str) -> int:
        raise NotImplementedError

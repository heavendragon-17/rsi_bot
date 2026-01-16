
from typing import Dict, Any, Optional, Sequence, Iterable
from decimal import Decimal
from app.core.interfaces import IFuturesExchange

class HyperliquidAdapter(IFuturesExchange):
    def __init__(self, config: dict):
        self.config = config

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> Sequence[Sequence[Any]]:
        return []

    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: Decimal,
        price: Optional[Decimal] = None,
        exit_reason: str = None
    ) -> Optional[Dict[str, Any]]:
        # Stub
        return None

    def get_balances(self, assets: Optional[Iterable[str]] = None) -> Dict[str, float]:
        return {}

    def get_balance_of(self, asset: str) -> float:
        return 0.0

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        return True

    def set_leverage(self, symbol: str, leverage: int) -> bool:
        return True

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        return None

    def place_stop_loss(self, symbol: str, amount: Decimal, trigger_price: Decimal) -> Optional[Dict[str, Any]]:
        return None

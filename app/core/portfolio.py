from typing import Dict, Optional, List
from app.core.interfaces import IExchange
from app.core.events import SignalEvent, OrderEvent
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class Position:
    symbol: str
    amount: float
    entry_price: float
    side: str # 'BUY' (Long) or 'SELL' (Short)
    timestamp: datetime

class PortfolioManager:
    def __init__(self, exchange: IExchange, config: dict):
        self.exchange = exchange
        self.config = config
        self.positions: Dict[str, Position] = {}
        # Risk settings
        self.max_position_size_pct = config.get('risk', {}).get('max_position_size_pct', 0.99)

    def sync_balance(self):
        """Sync balance from exchange (Real or Mock)"""
        return self.exchange.get_balance()

    def sync_positions(self):
        """Sync open positions from exchange"""
        # In a real scenario, we might reconcile local vs remote.
        # For now, we trust the exchange or track locally if exchange doesn't support easy retrieval.
        # Let's rely on local tracking for strategy logic but use exchange for execution.
        pass

    def on_signal(self, signal: SignalEvent) -> Optional[OrderEvent]:
        """
        Process a signal, apply risk checks, and execute order.
        """
        balance = self.sync_balance()

        if signal.signal_type == 'BUY':
            if signal.symbol in self.positions:
                print(f"Signal ignored: Already have position in {signal.symbol}")
                return None

            # Position Sizing
            amount_quote = balance * self.max_position_size_pct
            price = signal.price
            amount = amount_quote / price

            # Create Order
            order = self.exchange.create_order(
                symbol=signal.symbol,
                type='MARKET',
                side='BUY',
                amount=amount
            )

            if order:
                self.positions[signal.symbol] = Position(
                    symbol=signal.symbol,
                    amount=amount,
                    entry_price=price, # Should ideally come from order fill
                    side='BUY',
                    timestamp=signal.timestamp
                )
                print(f"Executed BUY for {signal.symbol} @ {price}")
                return order

        elif signal.signal_type == 'SELL':
            if signal.symbol not in self.positions:
                print(f"Signal ignored: No position to sell in {signal.symbol}")
                return None

            pos = self.positions[signal.symbol]

            # Create Order
            order = self.exchange.create_order(
                symbol=signal.symbol,
                type='MARKET',
                side='SELL',
                amount=pos.amount
            )

            if order:
                del self.positions[signal.symbol]
                print(f"Executed SELL for {signal.symbol} @ {signal.price}")
                return order

        return None

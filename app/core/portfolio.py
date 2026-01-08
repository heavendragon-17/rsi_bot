"""
Layer 3: Execution - Portfolio Manager
=======================================
Handles position management, order execution, TP/SL placement.
"""
from typing import Dict, Optional
from decimal import Decimal
from dataclasses import dataclass, field
from datetime import datetime

from app.core.interfaces import IExchange
from app.core.events import SignalEvent, OrderEvent


@dataclass
class Position:
    """
    Represents an open position with TP/SL tracking.
    """
    symbol: str
    amount: Decimal
    entry_price: Decimal
    side: str  # 'BUY' (Long)
    timestamp: datetime
    
    # TP/SL prices
    tp1_price: Optional[Decimal] = None
    tp2_price: Optional[Decimal] = None
    tp3_price: Optional[Decimal] = None
    sl_price: Optional[Decimal] = None
    
    # Order tracking
    sl_order_id: Optional[str] = None
    
    # TP hit tracking
    tp1_hit: bool = False
    tp2_hit: bool = False
    tp3_hit: bool = False


class PortfolioManager:
    """
    Manages positions, executes orders, and handles TP/SL.
    
    Features:
    - Position sizing based on balance percentage
    - Multi-level TP at R60, R70, R80
    - Limit SL order at R40 price
    """
    
    def __init__(self, exchange: IExchange, config: dict):
        self.exchange = exchange
        self.config = config
        self.positions: Dict[str, Position] = {}
        
        # Risk settings
        risk_cfg = config.get('risk', {})
        self.max_position_size_pct = Decimal(str(risk_cfg.get('max_position_size_pct', 0.99)))
        
        # TP percentages (how much to close at each level)
        self.tp1_close_pct = Decimal(str(risk_cfg.get('tp1_close_pct', 0.33)))  # 1/3 at R60
        self.tp2_close_pct = Decimal(str(risk_cfg.get('tp2_close_pct', 0.50)))  # 1/2 of remaining at R70
        # R80 = close 100% remaining

    def sync_balance(self) -> Decimal:
        """Get current balance from exchange."""
        return self.exchange.get_balance()

    def on_signal(self, signal: SignalEvent) -> Optional[OrderEvent]:
        """
        Process a trading signal.
        - BUY: Open position with limit SL order
        - SELL: Close position
        """
        self.sync_from_exchange()
        balance = self.sync_balance()

        if signal.signal_type == 'BUY':
            return self._handle_buy_signal(signal, balance)
        elif signal.signal_type == 'SELL':
            return self._handle_sell_signal(signal)
        
        return None

    def _handle_buy_signal(self, signal: SignalEvent, balance: Decimal) -> Optional[OrderEvent]:
        """Handle BUY signal - open position and place SL."""
        if signal.symbol in self.positions:
            print(f"Signal ignored: Already have position in {signal.symbol}")
            return None

        # Position sizing
        amount_quote = balance * self.max_position_size_pct
        price = signal.price
        amount = amount_quote / price

        # Execute market BUY order
        order = self.exchange.create_order(
            symbol=signal.symbol,
            order_type='MARKET',
            side='BUY',
            amount=amount
        )

        if order:
            # Create position
            self.positions[signal.symbol] = Position(
                symbol=signal.symbol,
                amount=amount,
                entry_price=price,
                side='BUY',
                timestamp=signal.timestamp,
                tp1_price=signal.tp1_price,
                tp2_price=signal.tp2_price,
                tp3_price=signal.tp3_price,
                sl_price=signal.sl_price,
            )
            
            # Place limit SL order if SL price is set
            if signal.sl_price is not None:
                sl_order = self.exchange.create_order(
                    symbol=signal.symbol,
                    order_type='LIMIT',
                    side='SELL',
                    amount=amount,
                    price=signal.sl_price
                )
                if sl_order:
                    self.positions[signal.symbol].sl_order_id = sl_order.get('id')
                    print(f"Placed limit SL order at {signal.sl_price}")
            
            print(f"Executed BUY for {signal.symbol} @ {price}")
            print(f"  TP1 (R60): {signal.tp1_price}")
            print(f"  TP2 (R70): {signal.tp2_price}")
            print(f"  TP3 (R80): {signal.tp3_price}")
            print(f"  SL (R40): {signal.sl_price}")
            
            return order

        return None

    def _handle_sell_signal(self, signal: SignalEvent) -> Optional[OrderEvent]:
        """Handle SELL signal - close position."""
        if signal.symbol not in self.positions:
            print(f"Signal ignored: No position to sell in {signal.symbol}")
            return None

        pos = self.positions[signal.symbol]

        # Cancel existing SL order if any
        if pos.sl_order_id:
            self.exchange.cancel_order(pos.sl_order_id, signal.symbol)

        # Execute market SELL order
        order = self.exchange.create_order(
            symbol=signal.symbol,
            order_type='MARKET',
            side='SELL',
            amount=pos.amount
        )

        if order:
            self.positions.pop(signal.symbol, None)
            print(f"Executed SELL for {signal.symbol} @ {signal.price}")
            return order

        return None

    def check_tp_levels(self, symbol: str, current_rsi: float, current_price: Decimal) -> Optional[str]:
        """
        Check if any TP level has been hit.
        Returns: 'TP1', 'TP2', 'TP3', or None
        
        Note: This should be called on each candle to monitor positions.
        """
        if symbol not in self.positions:
            return None
        
        pos = self.positions[symbol]
        
        # Check TP levels in order
        if not pos.tp1_hit and current_rsi >= 60:
            return 'TP1'
        if not pos.tp2_hit and current_rsi >= 70:
            return 'TP2'
        if current_rsi >= 80:
            return 'TP3'
        
        return None

    def execute_partial_close(self, symbol: str, tp_level: str) -> Optional[OrderEvent]:
        """
        Execute partial position close for TP level.
        
        - TP1: Close 1/3, move SL to entry
        - TP2: Close 1/2 of remaining (1/3 of original)
        - TP3: Close all remaining
        """
        if symbol not in self.positions:
            return None
        
        pos = self.positions[symbol]
        close_amount = Decimal("0")
        
        if tp_level == 'TP1' and not pos.tp1_hit:
            close_amount = pos.amount * self.tp1_close_pct
            pos.tp1_hit = True
            
            # Move SL to entry price
            if pos.sl_order_id:
                self.exchange.cancel_order(pos.sl_order_id, symbol)
            
            new_sl_order = self.exchange.create_order(
                symbol=symbol,
                order_type='LIMIT',
                side='SELL',
                amount=pos.amount - close_amount,
                price=pos.entry_price  # SL at entry (breakeven)
            )
            if new_sl_order:
                pos.sl_order_id = new_sl_order.get('id')
                print(f"Moved SL to entry price: {pos.entry_price}")
                
        elif tp_level == 'TP2' and not pos.tp2_hit:
            remaining = pos.amount * (Decimal("1") - self.tp1_close_pct) if pos.tp1_hit else pos.amount
            close_amount = remaining * self.tp2_close_pct
            pos.tp2_hit = True
            
        elif tp_level == 'TP3':
            # Close all remaining
            closed_so_far = Decimal("0")
            if pos.tp1_hit:
                closed_so_far += pos.amount * self.tp1_close_pct
            if pos.tp2_hit:
                remaining_after_tp1 = pos.amount - closed_so_far
                closed_so_far += remaining_after_tp1 * self.tp2_close_pct
            close_amount = pos.amount - closed_so_far
        
        if close_amount > 0:
            order = self.exchange.create_order(
                symbol=symbol,
                order_type='MARKET',
                side='SELL',
                amount=close_amount
            )
            
            if order:
                pos.amount -= close_amount
                print(f"Executed {tp_level} partial close: {close_amount} @ market")
                
                if pos.amount <= Decimal("0.00000001"):
                    # Position fully closed
                    if pos.sl_order_id:
                        self.exchange.cancel_order(pos.sl_order_id, symbol)
                    del self.positions[symbol]
                    print(f"Position fully closed for {symbol}")
                
                return order
        
        return None

    def has_position(self, symbol: str) -> bool:
        """Check if there's an open position for symbol."""
        return symbol in self.positions

    def get_position(self, symbol: str) -> Optional[Position]:
        """Get position details if exists."""
        return self.positions.get(symbol)
    
    def on_fill(self, trade: dict) -> None:
        """
        Sync portfolio internal state from an executed trade.
        Required because SL fills happen inside MockExchange (pending orders).
        """
        symbol = trade.get("symbol")
        side = trade.get("side")

        if not symbol or not side:
            return

        # If the exchange sold, position might be partially or fully closed.
        # In this backtest, SL closes the full remaining position -> remove it.
        if side == "SELL":
            pos = self.positions.get(symbol)
            if pos:
                # Clear local state
                self.positions.pop(symbol, None)


    def sync_from_exchange(self) -> None:
        """
        Make portfolio positions consistent with exchange positions.
        In backtest, SL limit fills can occur inside exchange without going through on_signal().
        """
        # Remove portfolio positions that no longer exist on exchange
        for sym in list(self.positions.keys()):
            if sym not in self.exchange.positions:
                self.positions.pop(sym, None)


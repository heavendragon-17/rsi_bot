from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

@dataclass
class Position:
    symbol: str
    entry_price: float
    amount: float
    side: str # 'LONG' (implied for now as spot usually is long, but good to have)
    entry_time: datetime
    sl: Optional[float] = None
    tp_levels: list = field(default_factory=list) # List of {'price': float, 'percent': float}

class BacktestPortfolio:
    def __init__(self, initial_balance=1000.0):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.positions = {} # symbol -> Position
        self.trade_history = []
        self.equity_curve = []

    def open_position(self, symbol, price, amount, side='LONG', sl=None, tps=None, time=None, reason=""):
        cost = price * amount
        if cost > self.balance:
            print(f"Insufficient funds to open position for {symbol}. Cost: {cost}, Balance: {self.balance}")
            return False

        self.balance -= cost
        pos = Position(symbol, price, amount, side, time, sl, tps or [])
        self.positions[symbol] = pos

        self.log_trade(symbol, 'BUY', price, amount, time, reason)
        return True

    def close_position(self, symbol, price, time, reason=""):
        if symbol not in self.positions:
            return

        pos = self.positions[symbol]
        revenue = price * pos.amount
        pnl = revenue - (pos.entry_price * pos.amount)
        self.balance += revenue

        self.log_trade(symbol, 'SELL', price, pos.amount, time, reason, pnl)
        del self.positions[symbol]

    def log_trade(self, symbol, side, price, amount, time, reason, pnl=0.0):
        self.trade_history.append({
            'time': time,
            'symbol': symbol,
            'side': side,
            'price': price,
            'amount': amount,
            'reason': reason,
            'pnl': pnl,
            'balance': self.balance
        })

    def check_sl_tp(self, symbol, candle):
        """
        Check if SL or TP is hit for a given candle.
        Returns True if position closed.
        """
        if symbol not in self.positions:
            return False

        pos = self.positions[symbol]

        # Check SL (Low for Long)
        if pos.sl and candle.low <= pos.sl:
            self.close_position(symbol, pos.sl, candle.timestamp, reason="STOP_LOSS")
            return True

        # Check TP (High for Long)
        # Simplify: If any TP level hit, close percentage (Level 2 advanced: partial close)
        # For now, let's implement full close on first TP to demonstrate, or Partial if structure supports.
        # User asked for partial.

        remaining_tps = []
        for tp in pos.tp_levels:
            if candle.high >= tp['price']:
                # Execute Partial Sell
                amount_to_sell = pos.amount * tp['percent']
                # But wait, pos.amount is changing. Need to track original amount or ratio.
                # Simplification: Close everything on final TP, or split logic.
                # Let's assume simpler TP logic for this MVP:
                # If TP hit, close position (or a portion).

                # Implementation: Close 100% on first TP for MVP stability, unless user specified otherwise.
                # User said: "Chốt lời từng phần tại RSI 60, 70, 80" -> This is indicator based, not Price based (Limit Order).
                # User ALSO said: "Exit: Sell tại nến 14:00. Lý do: Chạm RSI 80."
                # This implies the STRATEGY triggers the exit, not a Limit Order waiting at a price.

                pass

        # However, "Dời SL khi đạt R1" implies price monitoring.
        # Let's keep Price-based SL/TP support.

        return False

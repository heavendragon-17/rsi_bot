from app.core.interfaces import IExchange
from datetime import datetime

class MockExchange(IExchange):
    def __init__(self, initial_balance=1000.0):
        self.balance = initial_balance # Quote currency (USDT)
        self.positions = {} # symbol -> amount
        self.trade_history = []
        self.current_prices = {} # symbol -> price (updated by engine)

    def update_price(self, symbol, price, timestamp):
        """Called by BacktestEngine to update current market price"""
        self.current_prices[symbol] = {'price': price, 'time': timestamp}

    def get_balance(self) -> float:
        return self.balance

    def fetch_ohlcv(self, symbol, timeframe, limit):
        return [] # Not used in push-based backtest

    def create_order(self, symbol, type, side, amount, price=None):
        # In backtest, we assume 'price' is current market price if not specified
        # (Slippage simulation could happen here)

        current_data = self.current_prices.get(symbol)
        if not current_data:
            print(f"MockExchange: No price data for {symbol}")
            return None

        exec_price = price if price else current_data['price']
        timestamp = current_data['time']

        cost = exec_price * amount

        if side == 'BUY':
            if cost > self.balance:
                print(f"MockExchange: Insufficient funds. Cost: {cost}, Bal: {self.balance}")
                return None
            self.balance -= cost
            self.positions[symbol] = self.positions.get(symbol, 0) + amount
            pnl = 0

        elif side == 'SELL':
            current_pos = self.positions.get(symbol, 0)
            if amount > current_pos:
                 print(f"MockExchange: Insufficient position. Has: {current_pos}, Want: {amount}")
                 return None

            revenue = exec_price * amount
            self.balance += revenue
            self.positions[symbol] -= amount
            if self.positions[symbol] <= 0:
                del self.positions[symbol]

            # Calculate PnL requires tracking average entry price.
            # For simplicity in Mock Exchange (Level 2 simulation),
            # we track realized PnL in the Trade History, but calculating it correctly requires
            # holding separate lots or weighted average.
            # Simplified: Since strategy buys 100% and sells 100%, we can just log revenue.
            # Real reporting will reconstruct PnL from the history stream.
            pnl = 0 # Calculated by reporter

        trade = {
            'time': timestamp,
            'symbol': symbol,
            'side': side,
            'price': exec_price,
            'amount': amount,
            'cost_or_revenue': cost if side == 'BUY' else revenue,
            'balance_after': self.balance
        }
        self.trade_history.append(trade)
        return trade

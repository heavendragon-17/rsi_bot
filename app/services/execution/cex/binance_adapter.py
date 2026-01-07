from app.core.interfaces import IExchange
import ccxt
import os

class BinanceAdapter(IExchange):
    def __init__(self, config):
        self.config = config
        self.client = ccxt.binanceusdm({
            'apiKey': os.getenv('BINANCE_API_KEY'),
            'secret': os.getenv('BINANCE_SECRET_KEY')
        })
    
    def fetch_ohlcv(self, symbol, timeframe, limit):
        return self.client.fetch_ohlcv(symbol, timeframe, limit=limit)
        
    def create_order(self, symbol, type, side, amount, price=None):
        params = {}
        return self.client.create_order(symbol, type, side, amount, price, params)
    
    def get_balance(self) -> float:
        # Fetch USDT balance
        balance = self.client.fetch_balance()
        return balance['USDT']['total']

    def subcribe(self, symbols):
        pass # WebSocket handled by stream_manager

from app.core.interfaces import IExchange

class HyperliquidAdapter(IExchange):
    def __init__(self, config):
        self.config = config
        # SDK init here
    
    def fetch_ohlcv(self, symbol, timeframe, limit):
        raise NotImplementedError
        
    def create_order(self, symbol, type, side, amount, price=None):
        raise NotImplementedError

    def subcribe(self, symbols):
        pass

from .cex.binance_adapter import BinanceAdapter
from .dex.hyperliquid_adapter import HyperliquidAdapter

class ExchangeFactory:
    @staticmethod
    def create_exchange(config):
        exchange_name = config.get('exchange', {}).get('name', 'binance')
        if exchange_name == 'binance':
            return BinanceAdapter(config)
        elif exchange_name == 'hyperliquid':
            return HyperliquidAdapter(config)
        raise ValueError(f"Unknown exchange: {exchange_name}")

from abc import ABC, abstractmethod

class IExchange(ABC):
    @abstractmethod
    def fetch_ohlcv(self, symbol, timeframe, limit): pass

    @abstractmethod
    def create_order(self, symbol, type, side, amount, price=None):
        """
        Executes an order.
        Returns order details (dict) on success, None on failure.
        """
        pass

    @abstractmethod
    def get_balance(self) -> float:
        """
        Returns the total balance in Quote currency (e.g. USDT).
        """
        pass

class IStrategy(ABC):
    @abstractmethod
    def analyze(self, df): pass

class IDataProvider(ABC):
    @abstractmethod
    def subcribe(self, symbols): pass

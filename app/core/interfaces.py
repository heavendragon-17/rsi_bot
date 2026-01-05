from abc import ABC, abstractmethod

class IExchange(ABC):
    @abstractmethod
    def fetch_ohlcv(self, symbol, timeframe, limit): pass
    @abstractmethod
    def create_order(self, symbol, type, side, amount, price=None): pass

class IStrategy(ABC):
    @abstractmethod
    def analyze(self, df): pass

class IDataProvider(ABC):
    @abstractmethod
    def subcribe(self, symbols): pass

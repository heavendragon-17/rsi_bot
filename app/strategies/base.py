from abc import abstractmethod
from app.core.interfaces import IStrategy

class BaseStrategy(IStrategy):
    def __init__(self, config):
        self.config = config

    @abstractmethod
    def analyze(self, symbol, df):
        pass

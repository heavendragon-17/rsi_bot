from .backtest import BacktestAPIMixin
from .config import ConfigAPIMixin
from .data import DataAPIMixin

class BridgeAPI(BacktestAPIMixin, ConfigAPIMixin, DataAPIMixin):
    """Combined API exposed to JavaScript via PyWebView."""

    def __init__(self):
        print("BridgeAPI initialized")

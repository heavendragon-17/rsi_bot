from __future__ import annotations

from decimal import Decimal
import pandas as pd

from app.core.events import Candle
from app.services.market_data.store import MarketDataStore
from app.core.interfaces import IExchange


def load_latest_candles_into_store(
    exchange: IExchange,
    store: MarketDataStore,
    symbol: str,
    timeframe: str,
    limit: int = 500,
) -> None:
    """
    Fetch candles from exchange and push them into MarketDataStore.

    Fields:
      timestamp, open, high, low, close, volume
    """

    raw = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)

    for ts_ms, o, h, l, c, v in raw:
        candle = Candle(
            symbol=symbol,
            timestamp=pd.to_datetime(ts_ms, unit="ms", utc=True).to_pydatetime(),
            open=Decimal(str(o)),
            high=Decimal(str(h)),
            low=Decimal(str(l)),
            close=Decimal(str(c)),
            volume=Decimal(str(v)),
            closed=True,  # historical candles are closed
        )
        store.update_candle(candle)

import pandas as pd
import threading

MAX_CANDLES_IN_RAM = 300

class MarketDataStore:
    def __init__(self):
        self.data = {}
        self.lock = threading.Lock()

    def update_candle(self, candle):
        with self.lock:
            # candle is now a Candle object
            new_row = {
                'timestamp': candle.timestamp,
                'open': candle.open,
                'high': candle.high,
                'low': candle.low,
                'close': candle.close,
                'volume': candle.volume,
                'closed': candle.closed
            }

            symbol = candle.symbol

            if symbol not in self.data:
                df = pd.DataFrame([new_row])
                df.set_index('timestamp', inplace=True)
                self.data[symbol] = df
            else:
                df = self.data[symbol]
                last_time = df.index[-1]
                new_time = new_row['timestamp']

                if new_time == last_time:
                    # Update current candle
                    update_values = [
                        new_row['open'], new_row['high'], new_row['low'],
                        new_row['close'], new_row['volume'], new_row['closed']
                    ]
                    df.iloc[-1] = update_values
                else:
                    # New candle
                    new_df = pd.DataFrame([new_row])
                    new_df.set_index('timestamp', inplace=True)
                    self.data[symbol] = pd.concat([df, new_df])

                if len(self.data[symbol]) > MAX_CANDLES_IN_RAM:
                    self.data[symbol] = self.data[symbol].tail(MAX_CANDLES_IN_RAM)

    def get_dataframe(self, symbol):
        with self.lock:
            return self.data.get(symbol, None).copy() if symbol in self.data else None

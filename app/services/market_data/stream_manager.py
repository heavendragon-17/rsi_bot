import websocket
import threading
import json
import time
import ccxt
from app.core.events import MarketEvent, Candle, EventType
from .normalizer import DataNormalizer

STREAM_URL = "wss://fstream.binance.com/stream?streams="

class BinanceStreamManager:
    def __init__(self, symbols, timeframe, store):
        self.raw_symbols = symbols
        self.symbols = [s.lower().replace('/', '') for s in symbols]
        self.timeframe = timeframe
        self.store = store
        self.ws = None
        self.keep_running = True
        params = "/".join([f"{s}@kline_{self.timeframe}" for s in self.symbols])
        self.url = STREAM_URL + params

    def fetch_initial_data(self):
        print("Fetching initial historical data...")
        try:
            exchange = ccxt.binanceusdm()
            for symbol in self.raw_symbols:
                try:
                    # Fetch OHLCV
                    ohlcvs = exchange.fetch_ohlcv(symbol, self.timeframe, limit=300)
                    for ohlcv in ohlcvs:
                        # Normalize and update store
                        candle = DataNormalizer.normalize_ccxt(symbol, ohlcv)
                        self.store.update_candle(candle)
                    print(f"Fetched {len(ohlcvs)} candles for {symbol}")
                except Exception as e:
                    print(f"Error fetching history for {symbol}: {e}")
        except Exception as e:
            print(f"Error initializing CCXT client: {e}")

    def on_message(self, ws, message):
        json_msg = json.loads(message)
        if 'data' in json_msg:
            # 1. Normalize Data (Layer 1)
            event = DataNormalizer.normalize_binance(json_msg['data'])
            
            # 2. Update Store (Pass Payload)
            self.store.update_candle(event.payload)

    def on_error(self, ws, error):
        print(f"Websocket Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print("Websocket Disconnected")

    def on_open(self, ws):
        print(f"Websocket Connected: {self.symbols}")

    def start(self):
        # Fetch historical data before starting stream
        self.fetch_initial_data()

        def run():
            self.ws = websocket.WebSocketApp(self.url,
                                             on_open=self.on_open,
                                             on_message=self.on_message,
                                             on_error=self.on_error,
                                             on_close=self.on_close)
            while self.keep_running:
                self.ws.run_forever(ping_interval=60, ping_timeout=10)
                time.sleep(2)

        thread = threading.Thread(target=run)
        thread.daemon = True
        thread.start()

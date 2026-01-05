import websocket
import threading
import json
import time
from .normalizer import DataNormalizer

STREAM_URL = "wss://fstream.binance.com/stream?streams="

class BinanceStreamManager:
    def __init__(self, symbols, timeframe, store):
        self.symbols = [s.lower().replace('/', '') for s in symbols]
        self.timeframe = timeframe
        self.store = store
        self.ws = None
        self.keep_running = True
        params = "/".join([f"{s}@kline_{self.timeframe}" for s in self.symbols])
        self.url = STREAM_URL + params

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

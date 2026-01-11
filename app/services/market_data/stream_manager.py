# app/services/market_data/binance_stream_manager.py

from __future__ import annotations

import json
import threading
import time
from typing import List, Optional

import ccxt
import websocket

from .normalizer import DataNormalizer

STREAM_URL = "wss://fstream.binance.com/stream?streams="


class BinanceStreamManager:
    """
    Binance Futures (USDT-M) Stream Manager

    - Streams kline from: fstream.binance.com
    - Fetches initial history using: ccxt.binanceusdm()
    - Normalizes everything using DataNormalizer:
        * WS kline -> MarketEvent(Candle)
        * CCXT OHLCV -> Candle
    - Stores Candle into `store.update_candle(candle)`
    """

    def __init__(
        self,
        symbols: List[str],
        timeframe: str,
        store,
        history_limit: int = 300,
        enable_history: bool = True,
    ):
        self.raw_symbols = symbols
        self.timeframe = timeframe
        self.store = store
        self.history_limit = int(history_limit)
        self.enable_history = bool(enable_history)

        self.ws: Optional[websocket.WebSocketApp] = None
        self.keep_running = True

        # Convert input symbols to websocket stream symbols:
        # "BTC/USDT" -> "btcusdt"
        # "BTCUSDT"  -> "btcusdt"
        self.stream_symbols = [self._to_stream_symbol(s) for s in self.raw_symbols]

        params = "/".join([f"{s}@kline_{self.timeframe}" for s in self.stream_symbols])
        self.url = STREAM_URL + params

        # Futures historical fetch (match fstream)
        self.exchange = ccxt.binanceusdm({"enableRateLimit": True})

    # ----------------------------
    # symbol helpers
    # ----------------------------
    def _to_stream_symbol(self, symbol: str) -> str:
        """
        Convert:
          BTC/USDT -> btcusdt
          BTCUSDT  -> btcusdt
        """
        s = (symbol or "").strip().upper().replace("/", "")
        return s.lower()

    def _to_ccxt_symbol(self, symbol: str) -> str:
        """
        Convert:
          BTC/USDT -> BTC/USDT:USDT (USDT-M futures)
          BTCUSDT  -> BTC/USDT:USDT
          BTC/USDT:USDT -> BTC/USDT:USDT
        """
        s = (symbol or "").strip().upper()
        if not s:
            return s

        if ":" in s:
            return s

        if "/" not in s and s.endswith("USDT"):
            base = s[:-4]
            s = f"{base}/USDT"

        if s.endswith("/USDT"):
            return f"{s}:USDT"

        return s

    # ----------------------------
    # history
    # ----------------------------
    def fetch_initial_data(self) -> None:
        if not self.enable_history:
            return

        print("Fetching initial historical data (binanceusdm)...")
        try:
            self.exchange.load_markets()

            for symbol in self.raw_symbols:
                ccxt_symbol = self._to_ccxt_symbol(symbol)
                try:
                    ohlcvs = self.exchange.fetch_ohlcv(
                        ccxt_symbol, self.timeframe, limit=self.history_limit
                    )

                    # IMPORTANT:
                    # DataNormalizer.normalize_ccxt expects symbol like "BTC/USDT" (not with :USDT)
                    # because it strips quotes to base asset anyway.
                    # We'll pass the original user symbol so your normalizer remains consistent.
                    for ohlcv in ohlcvs:
                        candle = DataNormalizer.normalize_ccxt(symbol, ohlcv)
                        self.store.update_candle(candle)

                    print(f"Fetched {len(ohlcvs)} candles for {symbol} ({ccxt_symbol})")

                except Exception as e:
                    print(f"Error fetching history for {symbol}: {e}")

        except Exception as e:
            print(f"Error initializing CCXT futures client: {e}")

    # ----------------------------
    # websocket callbacks
    # ----------------------------
    def on_message(self, ws, message: str) -> None:
        try:
            json_msg = json.loads(message)
        except Exception:
            return

        data = json_msg.get("data")
        if not data:
            return

        # Normalize WS data -> MarketEvent(Candle)
        try:
            event = DataNormalizer.normalize_binance(data)
        except Exception as e:
            print(f"Normalizer error: {e}")
            return

        # store Candle
        self.store.update_candle(event.payload)

    def on_error(self, ws, error) -> None:
        print(f"Websocket Error: {error}")

    def on_close(self, ws, close_status_code, close_msg) -> None:
        print(f"Websocket Disconnected ({close_status_code}) {close_msg}")

    def on_open(self, ws) -> None:
        print(f"Websocket Connected: {self.stream_symbols} timeframe={self.timeframe}")

    # ----------------------------
    # lifecycle
    # ----------------------------
    def start(self) -> None:
        # Fetch history first
        self.fetch_initial_data()

        def run():
            while self.keep_running:
                try:
                    self.ws = websocket.WebSocketApp(
                        self.url,
                        on_open=self.on_open,
                        on_message=self.on_message,
                        on_error=self.on_error,
                        on_close=self.on_close,
                    )
                    # run_forever blocks until disconnect
                    self.ws.run_forever(ping_interval=60, ping_timeout=10)
                except Exception as e:
                    print(f"WS run_forever crashed: {e}")

                # reconnect delay
                if self.keep_running:
                    time.sleep(2)

        thread = threading.Thread(target=run, daemon=True)
        thread.start()

    def stop(self) -> None:
        self.keep_running = False
        try:
            if self.ws:
                self.ws.close()
        except Exception:
            pass

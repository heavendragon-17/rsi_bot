# app/services/market_data/binance_stream_manager.py

from __future__ import annotations

import json
import threading
import time
from collections.abc import Callable
from typing import Literal

import ccxt
import structlog
import websocket

from app.core.events import Candle

from .normalizer import DataNormalizer

logger = structlog.get_logger()

STREAM_URL = "wss://fstream.binance.com/market/stream?streams="


class BinanceStreamManager:
    """Binance USDT-M futures WebSocket stream manager.

    Supports two mutually-exclusive modes:

    * **Legacy (single-TF, live bot):**
      ``BinanceStreamManager(symbols, timeframe, store, ...)`` routes every
      WS candle to ``store.update_candle(candle)`` and fires
      ``on_kline_close`` / ``on_tick`` callbacks. History is fetched once
      per symbol; the callbacks do NOT fire for historical candles.

    * **Multi-TF (signal bot):**
      ``BinanceStreamManager(targets={(pair, tf), ...}, multiplexer=mux)``
      routes each candle to ``multiplexer.on_kline_event(pair, tf, candle)``.
      History is fetched per ``(pair, tf)`` and routed into the multiplexer.
    """

    def __init__(
        self,
        symbols: list[str] | None = None,
        timeframe: str | None = None,
        store=None,
        *,
        targets: set[tuple[str, str]] | None = None,
        multiplexer=None,
        history_limit: int = 300,
        enable_history: bool = True,
        history_complete_callback: Callable[[], None] | None = None,
    ):
        legacy_given = symbols is not None and timeframe is not None and store is not None
        multi_given = targets is not None and multiplexer is not None
        if legacy_given and multi_given:
            raise ValueError(
                "BinanceStreamManager: pass either (symbols, timeframe, store) "
                "or (targets, multiplexer), not both."
            )
        if not legacy_given and not multi_given:
            raise ValueError(
                "BinanceStreamManager: must pass either (symbols, timeframe, store) "
                "or (targets, multiplexer)."
            )

        self.history_limit = int(history_limit)
        self.enable_history = bool(enable_history)
        # Optional hook fired exactly once after all REST fetch attempts
        # return and before the WebSocket loop starts. Used by the signal
        # runtime to arm bootstrap-suppression gates (e.g. the BTC RSI
        # cross alert). Optional, so every existing caller is unchanged.
        self.history_complete_callback = history_complete_callback

        self.ws: websocket.WebSocketApp | None = None
        self.keep_running = True

        # Legacy live-bot callbacks. Only populated/used in the legacy path.
        self.on_kline_close: Callable[[Candle], None] | None = None
        self.on_tick: Callable[[Candle], None] | None = None

        self._mode: Literal["legacy", "multi"]
        self._by_ws_key: dict[tuple[str, str], str] = {}

        if legacy_given:
            # The legacy_given guard above already established these are set;
            # asserts narrow the types for mypy.
            assert symbols is not None and timeframe is not None
            self._mode = "legacy"
            self._targets: frozenset[tuple[str, str]] = frozenset(
                (s, timeframe) for s in symbols
            )
            self.store = store
            self.multiplexer = None
            self.raw_symbols = list(symbols)
            self.timeframe: str = timeframe
        else:
            assert targets is not None and multiplexer is not None
            self._mode = "multi"
            self._targets = frozenset(targets)
            self.store = None
            self.multiplexer = multiplexer
            self.raw_symbols = sorted({pair for pair, _ in self._targets})
            # Reverse map: (BINANCE_WS_SYMBOL_UPPER, interval) -> user-facing
            # pair. Lets ``on_message`` recover the caller's pair string from
            # the payload. Binance always sends uppercase ``s``, but we
            # uppercase for safety.
            self._by_ws_key = {
                (self._to_stream_symbol(pair).upper(), tf): pair
                for pair, tf in self._targets
            }

        params = "/".join(
            f"{self._to_stream_symbol(pair)}@kline_{tf}" for pair, tf in self._targets
        )
        self.url = STREAM_URL + params

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

        logger.info("fetching_history", pairs=sorted(self._targets))
        for pair, tf in sorted(self._targets):
            ccxt_symbol = self._to_ccxt_symbol(pair)
            try:
                ohlcvs = self.exchange.fetch_ohlcv(ccxt_symbol, tf, limit=self.history_limit)
                for ohlcv in ohlcvs:
                    candle = DataNormalizer.normalize_ccxt(pair, ohlcv, timeframe=tf)
                    if self._mode == "legacy":
                        assert self.store is not None
                        self.store.update_candle(candle)
                    else:
                        assert self.multiplexer is not None
                        self.multiplexer.on_kline_event(pair, tf, candle)
                logger.info("history_fetched", symbol=pair, timeframe=tf, candles=len(ohlcvs))
            except Exception as e:
                logger.error("history_fetch_error", symbol=pair, timeframe=tf, error=str(e))

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

        try:
            event = DataNormalizer.normalize_binance(data)
        except Exception as e:
            logger.error("normalizer_error", error=str(e))
            return

        candle = event.payload

        if self._mode == "legacy":
            assert self.store is not None
            self.store.update_candle(candle)
            if self.on_tick is not None:
                self.on_tick(candle)
            if candle.closed and self.on_kline_close is not None:
                self.on_kline_close(candle)
            return

        raw_symbol = data.get("s", "")
        user_pair = self._by_ws_key.get((raw_symbol, candle.timeframe))
        if user_pair is None:
            logger.debug(
                "stream_untargeted_message",
                raw_symbol=raw_symbol,
                interval=candle.timeframe,
            )
            return

        assert self.multiplexer is not None
        self.multiplexer.on_kline_event(user_pair, candle.timeframe, candle)

    def on_error(self, ws, error) -> None:
        logger.error("websocket_error", error=str(error))

    def on_close(self, ws, close_status_code, close_msg) -> None:
        logger.warning("websocket_disconnected", code=close_status_code, msg=close_msg)

    def on_open(self, ws) -> None:
        logger.info("websocket_connected", targets=sorted(self._targets))

    # ----------------------------
    # lifecycle
    # ----------------------------
    def _notify_history_complete(self) -> None:
        """Fire the optional history-complete hook exactly once.

        Runs after every target fetch attempt returned (failures swallowed
        by ``fetch_initial_data`` included) and before the WebSocket loop
        starts. Callback exceptions are isolated so the stream still starts.
        """
        if self.history_complete_callback is None:
            return
        try:
            self.history_complete_callback()
        except Exception as e:
            logger.exception("history_complete_callback_error", error=str(e))

    def start(self) -> None:
        # 1. Fetch REST history for every target.
        self.fetch_initial_data()

        # 2. Declare history loading complete (exactly once) — alert-only
        #    components arm their bootstrap gates here.
        self._notify_history_complete()

        # 3. Start the WebSocket loop.
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
                    logger.error("websocket_crashed", error=str(e))

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

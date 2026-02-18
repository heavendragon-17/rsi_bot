# app/paper/stream_manager.py
"""
PaperTradeStreamManager
=======================
Subscribes to Binance aggTrade combined WebSocket stream for all configured symbols.
Samples one price per 500 ms per symbol and forwards to PaperExchange.on_tick().

Runs in a dedicated daemon thread, isolated from the kline pipeline.

Reconnect strategy: exponential backoff (1s, 2s, 4s … max 30s).
Tick buffer is flushed on disconnect (safe — ticks are sampled, not accumulated).
"""
from __future__ import annotations

import json
import logging
import threading
import time
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, List

if TYPE_CHECKING:
    from app.paper.exchange import PaperExchange

logger = logging.getLogger(__name__)

_STREAM_BASE = "wss://fstream.binance.com/stream?streams="
_MAX_BACKOFF = 30.0


def _symbol_to_stream(symbol: str) -> str:
    """'BTC/USDT' → 'btcusdt@aggTrade'"""
    return symbol.replace("/", "").lower() + "@aggTrade"


def _stream_to_symbol(stream_symbol: str) -> str:
    """aggTrade 's' field is already like 'BTCUSDT' — convert to 'BTC/USDT' format
    by matching against the configured symbols list."""
    return stream_symbol  # raw Binance format; matched against _raw_symbols map


class PaperTradeStreamManager:
    """
    Subscribes to Binance aggTrade streams, samples 1 price/500ms per symbol,
    and calls PaperExchange.on_tick() for SL/TP fill detection.
    """

    def __init__(
        self,
        symbols: List[str],
        paper_exchange: "PaperExchange",
        tick_interval_ms: int = 500,
    ):
        self._symbols = symbols
        self._exchange = paper_exchange
        self._tick_interval = tick_interval_ms / 1000.0  # seconds

        # Build mapping: Binance raw symbol → normalised symbol (e.g. "BTCUSDT" → "BTC/USDT")
        self._raw_to_norm: Dict[str, str] = {
            s.replace("/", "").upper(): s for s in symbols
        }

        # Latest price buffer and last-sample timestamps (per symbol)
        self._buffers: Dict[str, Decimal] = {}
        self._last_sample: Dict[str, float] = {}

        self._ws = None
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the aggTrade stream in a background daemon thread."""
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_with_reconnect,
            name="PaperTickStream",
            daemon=True,
        )
        self._thread.start()
        logger.info(f"[PaperTradeStreamManager] Started for {len(self._symbols)} symbols")

    def stop(self) -> None:
        """Signal the stream thread to stop and close the WebSocket."""
        self._stop_event.set()
        if self._ws:
            try:
                self._ws.close()
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[PaperTradeStreamManager] Stopped")

    # ------------------------------------------------------------------
    # Reconnect loop
    # ------------------------------------------------------------------

    def _run_with_reconnect(self) -> None:
        backoff = 1.0
        while not self._stop_event.is_set():
            try:
                self._connect()
                backoff = 1.0  # reset on clean disconnect
            except Exception as exc:
                if self._stop_event.is_set():
                    break
                logger.warning(
                    f"[PaperTradeStreamManager] WebSocket error: {exc}. "
                    f"Reconnecting in {backoff:.0f}s…"
                )
                self._stop_event.wait(timeout=backoff)
                backoff = min(backoff * 2, _MAX_BACKOFF)

    def _connect(self) -> None:
        try:
            import websocket  # websocket-client
        except ImportError as exc:
            raise RuntimeError(
                "websocket-client is not installed. Run: pip install websocket-client"
            ) from exc

        streams = "/".join(_symbol_to_stream(s) for s in self._symbols)
        url = _STREAM_BASE + streams
        logger.info(f"[PaperTradeStreamManager] Connecting to {url[:80]}…")

        ws = websocket.WebSocketApp(
            url,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close,
        )
        self._ws = ws
        # run_forever blocks until disconnect
        ws.run_forever(ping_interval=20, ping_timeout=10)

    # ------------------------------------------------------------------
    # WebSocket callbacks
    # ------------------------------------------------------------------

    def _on_message(self, ws, raw: str) -> None:  # noqa: ARG002
        try:
            msg = json.loads(raw)
            # Combined stream format: {"stream": "btcusdt@aggTrade", "data": {...}}
            data = msg.get("data", msg)
            raw_sym = data.get("s", "")
            price_str = data.get("p", "")
            if not raw_sym or not price_str:
                return

            norm_sym = self._raw_to_norm.get(raw_sym.upper())
            if not norm_sym:
                return  # symbol not in our config

            price = Decimal(price_str)
            now = time.time()

            # Always update buffer with the latest price
            self._buffers[norm_sym] = price

            # Sample once per tick_interval
            last = self._last_sample.get(norm_sym, 0.0)
            if now - last >= self._tick_interval:
                self._last_sample[norm_sym] = now
                try:
                    self._exchange.on_tick(norm_sym, price, now)
                except Exception:
                    logger.exception(f"[PaperTradeStreamManager] on_tick error for {norm_sym}")
        except Exception:
            logger.exception("[PaperTradeStreamManager] _on_message parse error")

    def _on_error(self, ws, error) -> None:  # noqa: ARG002
        if not self._stop_event.is_set():
            logger.warning(f"[PaperTradeStreamManager] WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg) -> None:  # noqa: ARG002
        logger.info(
            f"[PaperTradeStreamManager] WebSocket closed "
            f"(code={close_status_code}, msg={close_msg})"
        )
        # Flush buffers — safe because ticks are sampled, not accumulated
        self._buffers.clear()
        self._last_sample.clear()

    def get_last_price(self, symbol: str) -> Decimal | None:
        """Return the most recently received price for a symbol (may lag up to 500ms)."""
        return self._buffers.get(symbol)

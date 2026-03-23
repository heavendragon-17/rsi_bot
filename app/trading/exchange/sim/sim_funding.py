# app/sim/funding.py
"""
SimFundingScheduler
=====================
Applies real Binance USDT-M funding rates to open sim positions
at 00:00, 08:00, and 16:00 UTC (every 8 hours).

Funding rate is fetched from the public Binance REST endpoint — no API key required.
On fetch failure: log warning and skip (no retry, no cached-rate fallback).

Runs in a single background daemon thread using threading.Event.wait()
to sleep until the next funding window.
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import requests  # type: ignore[import-untyped]
import structlog

if TYPE_CHECKING:
    from app.trading.exchange.sim.sim_state import SimTradeState

logger = structlog.get_logger(__name__)

_FUNDING_ENDPOINT = "https://fapi.binance.com/fapi/v1/premiumIndex"
_FUNDING_HOURS = (0, 8, 16)  # UTC hours when funding is applied
_REQUEST_TIMEOUT = 10  # seconds


def _seconds_to_next_funding() -> float:
    """Return seconds until the next funding window (00:00 / 08:00 / 16:00 UTC)."""
    now = datetime.now(UTC)
    current_hour = now.hour
    current_minute = now.minute
    current_second = now.second

    for h in _FUNDING_HOURS:
        if h > current_hour or (h == current_hour and (current_minute > 0 or current_second > 0)):
            target = now.replace(hour=h, minute=0, second=5, microsecond=0)
            return (target - now).total_seconds()

    # Next is 00:00 UTC tomorrow
    tomorrow_midnight = now.replace(hour=0, minute=0, second=5, microsecond=0)
    # Add one day
    from datetime import timedelta

    tomorrow_midnight += timedelta(days=1)
    return (tomorrow_midnight - now).total_seconds()


class SimFundingScheduler:
    """
    Background thread that applies Binance funding rates to open sim positions
    at each 8-hour funding window.
    """

    def __init__(self, state: SimTradeState, notification_service=None):
        self._state = state
        self._notification_service = notification_service
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name="SimFundingScheduler",
            daemon=True,
        )
        self._thread.start()
        logger.info("[SimFundingScheduler] Started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[SimFundingScheduler] Stopped")

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run(self) -> None:
        while not self._stop_event.is_set():
            wait_secs = _seconds_to_next_funding()
            logger.info(f"[SimFundingScheduler] Next funding in {wait_secs:.0f}s")
            # Wait until next funding window (or stop signal)
            self._stop_event.wait(timeout=wait_secs)
            if self._stop_event.is_set():
                break
            self.apply_funding()
            # Brief sleep to avoid double-firing at boundary
            time.sleep(2)

    def apply_funding(self) -> None:
        """Fetch rates from Binance and deduct funding from open sim positions."""
        with self._state.lock:
            symbols = list(self._state.positions.keys())

        if not symbols:
            logger.debug("[SimFundingScheduler] No open positions — skipping funding")
            return

        for symbol in symbols:
            try:
                rate = self._fetch_funding_rate(symbol)
            except Exception as exc:
                logger.warning(f"[SimFundingScheduler] Funding rate fetch failed for {symbol}: {exc}. Skipping.")
                continue

            with self._state.lock:
                pos = self._state.positions.get(symbol)
                if not pos:
                    continue
                last_price = Decimal(
                    str(
                        # Use entry price as fallback if no tick price available
                        pos.entry_price
                    )
                )
                notional = pos.amount * last_price
                payment = notional * rate  # positive → longs pay
                self._state.balance -= payment
                self._state.total_funding_paid += payment
                balance_after = self._state.balance

            logger.info(
                f"[SimFundingScheduler] {symbol} funding applied: "
                f"rate={float(rate):.6f}  payment={float(payment):.4f} USDT"
            )
            if self._notification_service:
                try:
                    self._notification_service.on_funding(
                        symbol=symbol,
                        rate=rate,
                        payment=payment,
                        balance=balance_after,
                    )
                except Exception:
                    logger.exception("[SimFundingScheduler] notification_service.on_funding error")

    def _fetch_funding_rate(self, symbol: str) -> Decimal:
        """
        Fetch current funding rate from Binance public API.
        Raises on any error (caller handles it with skip).
        """
        # Convert "BTC/USDT" → "BTCUSDT"
        raw_symbol = symbol.replace("/", "").upper()
        resp = requests.get(
            _FUNDING_ENDPOINT,
            params={"symbol": raw_symbol},
            timeout=_REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        data = resp.json()
        rate_str = data.get("lastFundingRate", "0")
        return Decimal(str(rate_str))

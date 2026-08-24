"""Venue-aware public historical data and reconnecting live polling.

Both implementations are credential-free.  Network I/O only occurs when
``fetch_closed`` or the poller lifecycle is invoked; importing and constructing
the objects is safe in offline tests.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from email.utils import parsedate_to_datetime
from typing import Any, Protocol

import ccxt
import requests
import structlog

from app.signal.core_v2_1.buffer import MarketDataIntegrityError
from app.signal.core_v2_1.models import (
    ClosedCandle,
    MarketKey,
    Venue,
    ensure_utc,
    timeframe_delta,
)

logger = structlog.get_logger(__name__)

DEFAULT_FINALIZATION_DELAY = timedelta(seconds=5)


class MarketDataSourceError(RuntimeError):
    """A public market-data request failed or returned malformed data."""


class _AuthoritativeClockCache:
    """Advance a recent venue-time sample with the monotonic host clock."""

    def __init__(self, *, refresh_seconds: float = 30.0) -> None:
        self._refresh_seconds = refresh_seconds
        self._lock = threading.Lock()
        self._sample: tuple[float, datetime] | None = None

    def resolve(self, fetch: Callable[[], datetime]) -> datetime:
        with self._lock:
            monotonic_now = time.monotonic()
            if self._sample is not None:
                sampled_monotonic, sampled_server = self._sample
                elapsed = monotonic_now - sampled_monotonic
                if elapsed <= self._refresh_seconds:
                    return sampled_server + timedelta(seconds=elapsed)
            server_now = ensure_utc(fetch(), field_name="venue server time")
            # Anchor at response completion.  Anchoring before a slow network
            # request would add that request latency again on the next cache
            # hit and could move the finalized-candle watermark into the
            # venue's still-forming boundary.
            sampled_monotonic = time.monotonic()
            self._sample = (sampled_monotonic, server_now)
            return server_now


class PublicCandleSource(Protocol):
    """Historical and latest fully-closed OHLCV source for one venue."""

    @property
    def venue(self) -> Venue: ...

    def resolve_server_now(self) -> datetime: ...

    def fetch_closed(
        self,
        key: MarketKey,
        start_close: datetime,
        end_close: datetime,
    ) -> tuple[ClosedCandle, ...]: ...


class CompositeMarketDataRouter:
    """Route by ``MarketKey.venue`` without symbol-name heuristics."""

    def __init__(self, sources: Iterable[PublicCandleSource]) -> None:
        by_venue: dict[Venue, PublicCandleSource] = {}
        for source in sources:
            if source.venue in by_venue:
                raise ValueError(f"Duplicate source for {source.venue.value}")
            by_venue[source.venue] = source
        if not by_venue:
            raise ValueError("At least one market-data source is required")
        self._sources = by_venue

    @property
    def venues(self) -> frozenset[Venue]:
        return frozenset(self._sources)

    def fetch_closed(
        self,
        key: MarketKey,
        start_close: datetime,
        end_close: datetime,
    ) -> tuple[ClosedCandle, ...]:
        try:
            source = self._sources[key.venue]
        except KeyError as exc:
            raise MarketDataSourceError(f"No source registered for {key.venue.value}") from exc
        start = ensure_utc(start_close, field_name="start_close")
        end = ensure_utc(end_close, field_name="end_close")
        candles = source.fetch_closed(key, start, end)
        for candle in candles:
            if candle.key != key:
                raise MarketDataSourceError(
                    f"Source for {key.storage_id} returned {candle.key.storage_id}"
                )
            if candle.close_time < start or candle.close_time > end:
                raise MarketDataSourceError(
                    f"Source returned out-of-window candle for {key.storage_id}: "
                    f"{candle.close_time.isoformat()} not in "
                    f"[{start.isoformat()}, {end.isoformat()}]"
                )
        return candles

    def finalized_through(
        self,
        *,
        venues: Iterable[Venue] | None = None,
        finalization_delay: timedelta = DEFAULT_FINALIZATION_DELAY,
    ) -> datetime:
        """Return a conservative cross-venue closed-candle watermark.

        Venue clocks are authoritative.  Taking the minimum ensures a mixed
        Binance/Hyperliquid bundle cannot advance because one venue (or the
        local host) is ahead of another.
        """

        if finalization_delay < timedelta(0):
            raise ValueError("finalization_delay cannot be negative")
        requested = set(venues) if venues is not None else set(self._sources)
        if not requested:
            raise ValueError("at least one venue is required for a watermark")
        unknown = requested - set(self._sources)
        if unknown:
            names = ", ".join(sorted(venue.value for venue in unknown))
            raise MarketDataSourceError(f"No time source registered for {names}")
        resolved = [
            ensure_utc(
                self._sources[venue].resolve_server_now(),
                field_name=f"{venue.value} server time",
            )
            for venue in requested
        ]
        return min(resolved) - finalization_delay


class BinancePublicCandleSource:
    """Credential-free Binance USDT-M OHLCV through CCXT public REST."""

    venue = Venue.BINANCE_FUTURES

    def __init__(
        self,
        *,
        exchange: Any | None = None,
        page_size: int = 1000,
        clock: Callable[[], datetime] | None = None,
        finalization_delay: timedelta = DEFAULT_FINALIZATION_DELAY,
    ) -> None:
        if page_size < 1:
            raise ValueError("page_size must be positive")
        if finalization_delay < timedelta(0):
            raise ValueError("finalization_delay cannot be negative")
        self._exchange = exchange
        self._page_size = page_size
        self._clock = clock
        self._finalization_delay = finalization_delay
        self._server_clock = _AuthoritativeClockCache()

    def _client(self) -> Any:
        if self._exchange is None:
            self._exchange = ccxt.binanceusdm({"enableRateLimit": True})
        return self._exchange

    def resolve_server_now(self) -> datetime:
        """Resolve Binance's public exchange clock without credentials."""

        if self._clock is not None:
            return ensure_utc(self._clock(), field_name="Binance server time")

        return self._server_clock.resolve(self._fetch_server_now)

    def _fetch_server_now(self) -> datetime:
        try:
            timestamp_ms = self._client().fetch_time()
            return datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=UTC)
        except Exception as exc:
            raise MarketDataSourceError(
                f"Could not resolve Binance server time: {exc}"
            ) from exc

    def fetch_closed(
        self,
        key: MarketKey,
        start_close: datetime,
        end_close: datetime,
    ) -> tuple[ClosedCandle, ...]:
        if key.venue is not self.venue:
            raise ValueError(f"Binance source cannot serve {key.venue.value}")
        finalized_now = self.resolve_server_now() - self._finalization_delay
        start, effective_end = _validated_window(
            start_close,
            end_close,
            finalized_now,
        )
        if start > effective_end:
            return ()

        duration = timeframe_delta(key.timeframe)
        duration_ms = _milliseconds(duration)
        cursor_open_ms = _to_ms(start - duration)
        end_open_ms = _to_ms(effective_end - duration)
        symbol = _binance_ccxt_symbol(key.instrument)
        result: dict[datetime, ClosedCandle] = {}

        while cursor_open_ms <= end_open_ms:
            try:
                rows = self._client().fetch_ohlcv(
                    symbol,
                    key.timeframe,
                    since=cursor_open_ms,
                    limit=self._page_size,
                )
            except Exception as exc:
                raise MarketDataSourceError(
                    f"Binance fetch failed for {key.storage_id}: {exc}"
                ) from exc
            if not rows:
                break

            progressed_to = cursor_open_ms
            for row in rows:
                candle = _ccxt_row_to_candle(key, row)
                progressed_to = max(progressed_to, _to_ms(candle.open_time) + duration_ms)
                if start <= candle.close_time <= effective_end:
                    _insert_unique_candle(result, candle, source_name="Binance")

            if progressed_to <= cursor_open_ms:
                raise MarketDataSourceError(
                    f"Binance returned a non-advancing page for {key.storage_id}"
                )
            cursor_open_ms = progressed_to

        return tuple(result[key_] for key_ in sorted(result))


class HyperliquidPublicCandleSource:
    """Official Hyperliquid ``candleSnapshot`` public REST source.

    The endpoint is public and this class intentionally accepts no wallet,
    private key, or account identifier.  A request can return at most 5,000
    recent candles globally.  Requests wider than that retention boundary, or
    requests whose first candle has already fallen out of retained history,
    fail explicitly instead of returning a deceptively partial series.  The
    same method supports recent historical catch-up and live polling.
    """

    venue = Venue.HYPERLIQUID_PERP
    DEFAULT_URL = "https://api.hyperliquid.xyz/info"

    def __init__(
        self,
        *,
        session: requests.Session | Any | None = None,
        url: str = DEFAULT_URL,
        timeout_seconds: float = 10.0,
        page_size: int = 5000,
        coin_by_instrument: dict[str, str] | None = None,
        clock: Callable[[], datetime] | None = None,
        finalization_delay: timedelta = DEFAULT_FINALIZATION_DELAY,
    ) -> None:
        if page_size < 1 or page_size > 5000:
            raise ValueError("Hyperliquid page_size must be in [1, 5000]")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if finalization_delay < timedelta(0):
            raise ValueError("finalization_delay cannot be negative")
        self._session = session or requests.Session()
        self._url = url
        self._timeout = timeout_seconds
        self._page_size = page_size
        self._coin_by_instrument = {
            key.upper(): value
            for key, value in (
                coin_by_instrument or {"PUMP/USDC:USDC": "PUMP"}
            ).items()
        }
        self._clock = clock
        self._finalization_delay = finalization_delay
        self._server_clock = _AuthoritativeClockCache()

    def resolve_server_now(self) -> datetime:
        """Read the public API gateway's RFC 7231 ``Date`` header."""

        if self._clock is not None:
            return ensure_utc(self._clock(), field_name="Hyperliquid server time")

        return self._server_clock.resolve(self._fetch_server_now)

    def _fetch_server_now(self) -> datetime:

        try:
            response = self._session.post(
                self._url,
                json={"type": "meta"},
                timeout=self._timeout,
            )
            response.raise_for_status()
            raw_date = response.headers.get("Date")
            if not raw_date:
                raise MarketDataSourceError("Hyperliquid response has no Date header")
            return ensure_utc(
                parsedate_to_datetime(raw_date),
                field_name="Hyperliquid server time",
            )
        except MarketDataSourceError:
            raise
        except Exception as exc:
            raise MarketDataSourceError(
                f"Could not resolve Hyperliquid server time: {exc}"
            ) from exc

    def fetch_closed(
        self,
        key: MarketKey,
        start_close: datetime,
        end_close: datetime,
    ) -> tuple[ClosedCandle, ...]:
        if key.venue is not self.venue:
            raise ValueError(f"Hyperliquid source cannot serve {key.venue.value}")
        finalized_now = self.resolve_server_now() - self._finalization_delay
        start, effective_end = _validated_window(
            start_close,
            end_close,
            finalized_now,
        )
        if start > effective_end:
            return ()

        duration = timeframe_delta(key.timeframe)
        duration_ms = _milliseconds(duration)
        cursor_open_ms = _to_ms(start - duration)
        end_open_ms = _to_ms(effective_end - duration)
        coin = self._coin_for(key.instrument)
        result: dict[datetime, ClosedCandle] = {}

        requested_candles = ((end_open_ms - cursor_open_ms) // duration_ms) + 1
        if requested_candles > self._page_size:
            raise MarketDataSourceError(
                f"Hyperliquid retains at most {self._page_size} recent "
                f"{key.timeframe} candles; request needs {requested_candles}"
            )

        payload = {
            "type": "candleSnapshot",
            "req": {
                "coin": coin,
                "interval": key.timeframe,
                "startTime": cursor_open_ms,
                "endTime": end_open_ms,
            },
        }
        try:
            response = self._session.post(
                self._url,
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
            rows = response.json()
        except Exception as exc:
            raise MarketDataSourceError(
                f"Hyperliquid fetch failed for {key.storage_id}: {exc}"
            ) from exc
        if not isinstance(rows, list):
            raise MarketDataSourceError("Hyperliquid candleSnapshot did not return a list")

        for raw in rows:
            candle = self._row_to_candle(key, raw)
            if start <= candle.close_time <= effective_end:
                _insert_unique_candle(result, candle, source_name="Hyperliquid")

        if not result:
            raise MarketDataSourceError(
                f"Hyperliquid returned no retained candles for {key.storage_id}"
            )
        first_close = min(result)
        expected_first_close = _ceil_utc_boundary(start, duration)
        if first_close > expected_first_close:
            raise MarketDataSourceError(
                f"Requested start {start.isoformat()} predates Hyperliquid "
                f"retained coverage beginning {first_close.isoformat()}"
            )

        return tuple(result[key_] for key_ in sorted(result))

    def _coin_for(self, instrument: str) -> str:
        compact = instrument.upper()
        try:
            return self._coin_by_instrument[compact]
        except KeyError as exc:
            raise MarketDataSourceError(
                f"No Hyperliquid coin mapping for source instrument {instrument!r}"
            ) from exc

    @staticmethod
    def _row_to_candle(key: MarketKey, raw: Any) -> ClosedCandle:
        if not isinstance(raw, dict):
            raise MarketDataSourceError("Hyperliquid candle row must be an object")
        required = ("t", "o", "h", "l", "c", "v")
        missing = [name for name in required if name not in raw]
        if missing:
            raise MarketDataSourceError(
                f"Hyperliquid candle is missing fields: {', '.join(missing)}"
            )
        try:
            open_time = datetime.fromtimestamp(int(raw["t"]) / 1000, tz=UTC)
            return ClosedCandle(
                key=key,
                open_time=open_time,
                close_time=open_time + timeframe_delta(key.timeframe),
                open=Decimal(str(raw["o"])),
                high=Decimal(str(raw["h"])),
                low=Decimal(str(raw["l"])),
                close=Decimal(str(raw["c"])),
                volume=Decimal(str(raw["v"])),
            )
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise MarketDataSourceError(f"Malformed Hyperliquid candle: {raw!r}") from exc


class PollCycleError(MarketDataSourceError):
    """One or more venue markets failed in a polling cycle."""


class ReconnectingClosedCandlePoller:
    """Catch-up polling feed with gap detection and exponential reconnect.

    Polling is intentional for the 15-minute Core V2.1 cadence: every request
    overlaps previous history, only canonical closes are emitted, and a
    disconnect is repaired chronologically before a later candle can pass.
    """

    def __init__(
        self,
        router: CompositeMarketDataRouter,
        keys: Iterable[MarketKey],
        on_candle: Callable[[ClosedCandle], None],
        *,
        poll_interval_seconds: float = 15.0,
        initial_backfill_candles: int = 3,
        max_backoff_seconds: float = 60.0,
        clock: Callable[[], datetime] | None = None,
        finalization_delay: timedelta = DEFAULT_FINALIZATION_DELAY,
    ) -> None:
        keys_tuple = tuple(sorted(set(keys)))
        if not keys_tuple:
            raise ValueError("poller needs at least one market key")
        if poll_interval_seconds <= 0 or max_backoff_seconds <= 0:
            raise ValueError("poll and backoff intervals must be positive")
        if initial_backfill_candles < 1:
            raise ValueError("initial_backfill_candles must be positive")
        if finalization_delay < timedelta(0):
            raise ValueError("finalization_delay cannot be negative")
        self._router = router
        self._keys = keys_tuple
        self._on_candle = on_candle
        self._poll_interval = poll_interval_seconds
        self._initial_backfill = initial_backfill_candles
        self._max_backoff = max_backoff_seconds
        self._clock = clock
        self._finalization_delay = finalization_delay
        self._venues = frozenset(key.venue for key in keys_tuple)
        self._last_emitted: dict[MarketKey, datetime] = {}
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lifecycle_lock = threading.Lock()
        self._health_lock = threading.Lock()
        self._last_error: str | None = None
        self._last_success_at: datetime | None = None
        self._has_completed_cycle = False

    @property
    def is_alive(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_ready(self) -> bool:
        with self._health_lock:
            return self._has_completed_cycle and self._last_error is None

    @property
    def last_error(self) -> str | None:
        with self._health_lock:
            return self._last_error

    @property
    def last_success_at(self) -> datetime | None:
        with self._health_lock:
            return self._last_success_at

    def seed_cursor(self, key: MarketKey, closed_at: datetime) -> None:
        if key not in self._keys:
            raise KeyError(key)
        self._last_emitted[key] = ensure_utc(closed_at, field_name="closed_at")

    def poll_once(self) -> int:
        if self._clock is None:
            now = self._router.finalized_through(
                venues=self._venues,
                finalization_delay=self._finalization_delay,
            )
        else:
            server_now = ensure_utc(self._clock(), field_name="server clock")
            now = server_now - self._finalization_delay
        pending: list[ClosedCandle] = []
        errors: list[str] = []
        for key in self._keys:
            try:
                pending.extend(self._fetch_key(key, now))
            except Exception as exc:
                logger.warning(
                    "core_v2_market_poll_failed",
                    market=key.storage_id,
                    error=str(exc),
                )
                errors.append(f"{key.storage_id}: {exc}")
        if errors:
            error = "; ".join(errors)
            with self._health_lock:
                self._last_error = error
            raise PollCycleError(error)

        # At a shared boundary (for example 12:00 UTC), slower dependencies
        # must enter the buffer before the M15 trigger.  The coordinator also
        # keeps a pending trigger cursor, but ordering here avoids needless
        # fail-closed/retry cycles.
        pending.sort(
            key=lambda candle: (
                candle.close_time,
                -timeframe_delta(candle.key.timeframe).total_seconds(),
                candle.key.storage_id,
            )
        )
        emitted = 0
        for candle in pending:
            current = self._last_emitted.get(candle.key)
            duration = timeframe_delta(candle.key.timeframe)
            if current is not None and candle.close_time != current + duration:
                raise MarketDataIntegrityError(
                    f"Non-contiguous live candle for {candle.key.storage_id}"
                )
            try:
                self._on_candle(candle)
            except Exception as exc:
                # Do not advance this key.  The next cycle re-fetches and
                # retries the same close after the callback/coordinator heals.
                error = (
                    f"callback failed for {candle.key.storage_id} at "
                    f"{candle.close_time.isoformat()}: {exc}"
                )
                with self._health_lock:
                    self._last_error = error
                raise PollCycleError(error) from exc
            self._last_emitted[candle.key] = candle.close_time
            emitted += 1
        with self._health_lock:
            self._last_error = None
            self._last_success_at = now
            self._has_completed_cycle = True
        return emitted

    def start(self) -> None:
        with self._lifecycle_lock:
            if self._thread is not None and self._thread.is_alive():
                if self._stop.is_set():
                    raise RuntimeError("Core V2.1 market poller shutdown is still in progress")
                return
            self._stop.clear()
            with self._health_lock:
                self._has_completed_cycle = False
                self._last_error = None
                self._last_success_at = None
            self._thread = threading.Thread(
                target=self._run,
                name="core-v2-market-poller",
                daemon=True,
            )
            self._thread.start()

    def stop(self, *, timeout_seconds: float = 10.0) -> None:
        if timeout_seconds < 0:
            raise ValueError("timeout_seconds cannot be negative")
        with self._lifecycle_lock:
            self._stop.set()
            thread = self._thread
            if thread is None:
                return
            thread.join(timeout=timeout_seconds)
            if thread.is_alive():
                raise TimeoutError(
                    "Core V2.1 market poller did not stop before the timeout"
                )
            self._thread = None

    def _run(self) -> None:
        backoff = self._poll_interval
        while not self._stop.is_set():
            try:
                self.poll_once()
                backoff = self._poll_interval
                self._stop.wait(self._poll_interval)
            except Exception as exc:
                with self._health_lock:
                    self._last_error = str(exc)
                logger.exception("core_v2_market_poll_cycle_failed", error=str(exc))
                self._stop.wait(min(backoff, self._max_backoff))
                backoff = min(backoff * 2, self._max_backoff)

    def _fetch_key(self, key: MarketKey, now: datetime) -> list[ClosedCandle]:
        duration = timeframe_delta(key.timeframe)
        expected_latest = _floor_utc_boundary(now, duration)
        previous = self._last_emitted.get(key)
        if previous is not None and previous > expected_latest:
            raise MarketDataIntegrityError(
                f"Live cursor for {key.storage_id} is ahead of the latest finalized "
                f"close {expected_latest.isoformat()}"
            )
        if previous is None:
            start = now - duration * self._initial_backfill
        else:
            # Inclusive request deliberately overlaps the prior candle.
            start = previous
        candles = tuple(
            sorted(
                self._router.fetch_closed(key, start, now),
                key=lambda candle: candle.close_time,
            )
        )
        if not candles:
            raise MarketDataIntegrityError(
                f"Live source returned no closed candles for {key.storage_id}; "
                f"expected latest finalized close {expected_latest.isoformat()}"
            )
        candidates = [
            candle
            for candle in candles
            if candle.close_time <= now
            and (previous is None or candle.close_time > previous)
        ]
        candidates.sort(key=lambda item: item.close_time)
        if previous is not None:
            expected = previous + duration
            for candle in candidates:
                if candle.close_time != expected:
                    raise MarketDataIntegrityError(
                        f"Live catch-up gap for {key.storage_id}: expected "
                        f"{expected.isoformat()}, got {candle.close_time.isoformat()}"
                    )
                expected += duration
        if candles[-1].close_time != expected_latest:
            raise MarketDataIntegrityError(
                f"Live source tail is stale for {key.storage_id}: expected latest "
                f"finalized close {expected_latest.isoformat()}, got "
                f"{candles[-1].close_time.isoformat()}"
            )
        if previous is not None and previous < expected_latest:
            if not candidates or candidates[-1].close_time != expected_latest:
                raise MarketDataIntegrityError(
                    f"Live catch-up is incomplete for {key.storage_id}: expected "
                    f"{expected_latest.isoformat()} after {previous.isoformat()}"
                )

        return candidates


def _validated_window(
    start_close: datetime,
    end_close: datetime,
    now: datetime,
) -> tuple[datetime, datetime]:
    start = ensure_utc(start_close, field_name="start_close")
    end = ensure_utc(end_close, field_name="end_close")
    now_utc = ensure_utc(now, field_name="clock")
    if end < start:
        raise ValueError("end_close must not precede start_close")
    return start, min(end, now_utc)


def _binance_ccxt_symbol(instrument: str) -> str:
    # MarketKey validates the structural unified symbol; retaining it exactly
    # avoids PUMPUSDC/PUMPUSDT-style alias ambiguity in venue routing.
    return instrument.upper()


def _ccxt_row_to_candle(key: MarketKey, row: Sequence[Any]) -> ClosedCandle:
    if len(row) < 6:
        raise MarketDataSourceError(f"Malformed CCXT OHLCV row: {row!r}")
    try:
        open_time = datetime.fromtimestamp(int(row[0]) / 1000, tz=UTC)
        return ClosedCandle(
            key=key,
            open_time=open_time,
            close_time=open_time + timeframe_delta(key.timeframe),
            open=Decimal(str(row[1])),
            high=Decimal(str(row[2])),
            low=Decimal(str(row[3])),
            close=Decimal(str(row[4])),
            volume=Decimal(str(row[5])),
        )
    except (TypeError, ValueError, ArithmeticError) as exc:
        raise MarketDataSourceError(f"Malformed CCXT OHLCV row: {row!r}") from exc


def _insert_unique_candle(
    result: dict[datetime, ClosedCandle],
    candle: ClosedCandle,
    *,
    source_name: str,
) -> None:
    existing = result.get(candle.close_time)
    if existing is not None and existing != candle:
        raise MarketDataSourceError(
            f"{source_name} returned conflicting duplicate candle for "
            f"{candle.key.storage_id} at {candle.close_time.isoformat()}"
        )
    result.setdefault(candle.close_time, candle)


def _milliseconds(value: timedelta) -> int:
    return int(value.total_seconds() * 1000)


def _to_ms(value: datetime) -> int:
    return int(ensure_utc(value, field_name="timestamp").timestamp() * 1000)


def _ceil_utc_boundary(value: datetime, duration: timedelta) -> datetime:
    utc_value = ensure_utc(value, field_name="boundary")
    seconds = int(duration.total_seconds())
    epoch_seconds = int(utc_value.timestamp())
    quotient, remainder = divmod(epoch_seconds, seconds)
    if remainder:
        quotient += 1
    return datetime.fromtimestamp(quotient * seconds, tz=UTC)


def _floor_utc_boundary(value: datetime, duration: timedelta) -> datetime:
    utc_value = ensure_utc(value, field_name="boundary")
    seconds = int(duration.total_seconds())
    epoch_seconds = int(utc_value.timestamp())
    return datetime.fromtimestamp((epoch_seconds // seconds) * seconds, tz=UTC)

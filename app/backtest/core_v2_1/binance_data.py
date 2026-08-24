"""Closed-candle Binance reconciliation for the Core V2.1 data window.

The CLI intentionally performs no work on import.  A caller supplies a CCXT
client (or compatible test double), making the reconciliation logic fully
testable offline.  Each refresh replaces the most recent closed M15 window,
bridges a stale legacy file when needed, preserves older rows, and commits only
after exact-cadence validation succeeds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Protocol

import pandas as pd
import structlog

from app.backtest.core_v2_1.coverage import BINANCE_BENCHMARK, CORE_V2_1_UNIVERSE, venue_for_symbol
from app.backtest.core_v2_1.data import (
    OHLCV_COLUMNS,
    STORED_UTC_OFFSET,
    CandleDataError,
    canonical_to_stored,
    normalize_stored_candles,
    timeframe_delta,
)
from app.trading.strategy.core_v2_1 import (
    FEATURE_ANCHOR_M15_OPEN,
    FEATURE_ANCHOR_VERSION,
)

logger = structlog.get_logger()
DEFAULT_RECENT_CANDLES = 5_000
MAX_PAGE_SIZE = 1_000
DEFAULT_FINALIZATION_DELAY = pd.Timedelta(seconds=5)
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / "data"


class BinanceDataError(RuntimeError):
    """Raised when Binance cannot provide a complete requested candle range."""


class OhlcvClient(Protocol):
    """Subset of the synchronous CCXT exchange API used by the reconciler."""

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        since: int | None = None,
        limit: int | None = None,
        params: dict[str, Any] | None = None,
    ) -> Sequence[Sequence[float]]: ...


@dataclass(frozen=True)
class BinanceRefreshResult:
    symbol: str
    venue_symbol: str
    path: str
    server_now: str
    recent_window_open_at: str
    requested_fetch_open_at: str
    last_closed_at: str
    recent_candles: int
    fetched_candles: int
    bridged_candles: int
    preserved_older_candles: int
    total_candles: int
    sha256: str
    feature_anchor_version: str
    feature_anchor_open_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def approved_binance_symbols() -> tuple[str, ...]:
    """The 24 Binance alts plus the Binance BTC benchmark."""

    alts = tuple(
        symbol for symbol in CORE_V2_1_UNIVERSE if venue_for_symbol(symbol) == "BINANCE_FUTURES"
    )
    return (*alts, BINANCE_BENCHMARK)


def ccxt_binance_perp_symbol(symbol: str) -> str:
    """Translate a normalized identity to CCXT's linear-perpetual notation."""

    normalized = symbol.upper().replace("/", "").split(":", maxsplit=1)[0]
    for quote in ("USDT", "USDC"):
        if normalized.endswith(quote) and len(normalized) > len(quote):
            base = normalized[: -len(quote)]
            return f"{base}/{quote}:{quote}"
    raise BinanceDataError(f"Unsupported Binance perpetual symbol identity: {symbol!r}")


def resolve_server_now(exchange: Any) -> pd.Timestamp:
    """Read Binance's authoritative exchange clock or fail closed."""

    fetch_time = getattr(exchange, "fetch_time", None)
    if not callable(fetch_time):
        raise BinanceDataError(
            "Binance authoritative server time is unavailable: CCXT fetch_time is not callable"
        )
    try:
        value = fetch_time()
        if value is None:
            raise ValueError("fetch_time returned no timestamp")
        return pd.Timestamp(int(value), unit="ms", tz="UTC")
    except Exception as exc:
        raise BinanceDataError(
            f"Could not resolve Binance authoritative server time: {exc}"
        ) from exc


def refresh_recent_closed_candles(
    exchange: OhlcvClient,
    *,
    symbol: str,
    data_dir: str | Path,
    candle_count: int = DEFAULT_RECENT_CANDLES,
    timeframe: str = "15m",
    server_now: pd.Timestamp | str | None = None,
    bridge_stale_history: bool = True,
    finalization_delay: pd.Timedelta = DEFAULT_FINALIZATION_DELAY,
) -> BinanceRefreshResult:
    """Refresh and atomically reconcile the latest fully closed candle window.

    The requested recent window is always fetched in full, even if it overlaps
    a local file, so Binance is authoritative for revised rows.  When a local
    file ends before that window, ``bridge_stale_history`` fetches the missing
    middle interval as well; this preserves older history without introducing
    an interior gap.
    """

    if candle_count <= 0:
        raise ValueError("candle_count must be positive")
    if finalization_delay < pd.Timedelta(0):
        raise ValueError("finalization_delay cannot be negative")
    delta = timeframe_delta(timeframe)
    if timeframe.lower() != "15m":
        raise BinanceDataError("Core V2.1 acquisition currently supports only the canonical 15m source")
    normalized = symbol.upper().replace("/", "").split(":", maxsplit=1)[0]
    if normalized not in approved_binance_symbols():
        raise BinanceDataError(f"{normalized} is not an approved Core V2.1 Binance identity")

    now = _aware_utc(server_now) if server_now is not None else resolve_server_now(exchange)
    # A small exchange-finalization delay prevents a boundary candle from
    # becoming immutable while its final OHLCV is still settling.
    closed_boundary = (now - finalization_delay).floor("15min")
    anchor_open = pd.Timestamp(FEATURE_ANCHOR_M15_OPEN)
    if closed_boundary <= anchor_open:
        raise BinanceDataError(
            "Authoritative Binance time has not reached the locked feature anchor"
        )
    recent_start = max(closed_boundary - candle_count * delta, anchor_open)
    output_dir = Path(data_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{normalized}_{timeframe.lower()}.csv"

    existing = _load_existing(output_path, now=now)
    if existing.empty:
        # Binance is pageable, so a fresh install always acquires the entire
        # immutable seed range even after it grows beyond the rolling window.
        fetch_start = anchor_open
    else:
        _require_existing_feature_anchor(existing, symbol=normalized)
        fetch_start = recent_start
    repair_start = _first_repair_open(existing, delta)
    if repair_start is not None and repair_start < fetch_start:
        fetch_start = repair_start
    if bridge_stale_history and not existing.empty:
        last_existing_open = existing.index[-1] - delta
        next_missing_open = last_existing_open + delta
        if next_missing_open < recent_start:
            fetch_start = next_missing_open

    fetched = _fetch_exact_range(
        exchange,
        venue_symbol=ccxt_binance_perp_symbol(normalized),
        timeframe=timeframe,
        start_open=fetch_start,
        end_open=closed_boundary,
        server_now=now,
    )
    expected_recent = pd.date_range(
        start=recent_start + delta,
        end=closed_boundary,
        freq=delta,
        tz="UTC",
        name="closed_at",
    )
    recent = fetched.loc[(fetched.index > recent_start) & (fetched.index <= closed_boundary)]
    if not recent.index.equals(expected_recent):
        missing = expected_recent.difference(recent.index)
        raise BinanceDataError(
            f"{normalized} recent window is incomplete: expected {len(expected_recent)}, got {len(recent)}, "
            f"missing={len(missing)}"
        )

    preserved = existing.loc[existing.index <= fetch_start]
    # If fetch_start is itself the next missing open, its close is +delta; the
    # preserved condition intentionally retains only candles strictly before
    # the first fetched close.  Duplicate safety below handles overlap.
    combined = pd.concat([preserved, fetched]).sort_index()
    combined = combined.loc[~combined.index.duplicated(keep="last")]
    stored = canonical_to_stored(combined, timeframe=timeframe)

    # Round-trip through the storage contract before replacing the user's file.
    # This validates the full preserved+bridged series, not only the new page.
    validated = normalize_stored_candles(stored, timeframe=timeframe, now=now, strict=True)
    if len(validated.frame) != len(combined):
        raise BinanceDataError("Closed-candle validation changed the reconciled row count")
    _require_existing_feature_anchor(validated.frame, symbol=normalized)
    _atomic_csv(output_path, stored)
    digest = hashlib.sha256(output_path.read_bytes()).hexdigest()

    bridged = max(0, int((recent_start - fetch_start) / delta))
    return BinanceRefreshResult(
        symbol=normalized,
        venue_symbol=ccxt_binance_perp_symbol(normalized),
        path=str(output_path.resolve()),
        server_now=now.isoformat(),
        recent_window_open_at=recent_start.isoformat(),
        requested_fetch_open_at=fetch_start.isoformat(),
        last_closed_at=closed_boundary.isoformat(),
        recent_candles=len(expected_recent),
        fetched_candles=len(fetched),
        bridged_candles=bridged,
        preserved_older_candles=len(preserved),
        total_candles=len(combined),
        sha256=digest,
        feature_anchor_version=FEATURE_ANCHOR_VERSION,
        feature_anchor_open_at=anchor_open.isoformat(),
    )


def refresh_approved_binance_universe(
    exchange: OhlcvClient,
    *,
    data_dir: str | Path,
    symbols: Sequence[str] | None = None,
    candle_count: int = DEFAULT_RECENT_CANDLES,
    server_now: pd.Timestamp | str | None = None,
) -> tuple[BinanceRefreshResult, ...]:
    """Refresh an approved subset, sharing one server-time boundary."""

    selected = tuple(symbol.upper() for symbol in (symbols or approved_binance_symbols()))
    unknown = tuple(symbol for symbol in selected if symbol not in approved_binance_symbols())
    if unknown:
        raise BinanceDataError(f"Unapproved Binance symbol(s): {', '.join(unknown)}")
    boundary_now = _aware_utc(server_now) if server_now is not None else resolve_server_now(exchange)
    results: list[BinanceRefreshResult] = []
    for symbol in selected:
        logger.info("core_v2_1_binance_refresh_started", symbol=symbol, candle_count=candle_count)
        result = refresh_recent_closed_candles(
            exchange,
            symbol=symbol,
            data_dir=data_dir,
            candle_count=candle_count,
            server_now=boundary_now,
        )
        results.append(result)
        logger.info("core_v2_1_binance_refresh_complete", **result.to_dict())
    return tuple(results)


def _fetch_exact_range(
    exchange: OhlcvClient,
    *,
    venue_symbol: str,
    timeframe: str,
    start_open: pd.Timestamp,
    end_open: pd.Timestamp,
    server_now: pd.Timestamp,
) -> pd.DataFrame:
    delta = timeframe_delta(timeframe)
    cursor = start_open
    rows: list[Sequence[float]] = []
    while cursor < end_open:
        remaining = int((end_open - cursor) / delta)
        page_limit = min(MAX_PAGE_SIZE, remaining)
        page = exchange.fetch_ohlcv(
            venue_symbol,
            timeframe,
            since=int(cursor.timestamp() * 1_000),
            limit=page_limit,
            params={"endTime": int(end_open.timestamp() * 1_000) - 1},
        )
        if not page:
            break
        in_range = [
            row
            for row in page
            if len(row) >= 6
            and int(cursor.timestamp() * 1_000) <= int(row[0]) < int(end_open.timestamp() * 1_000)
            and pd.Timestamp(int(row[0]), unit="ms", tz="UTC") + delta <= server_now
        ]
        if not in_range:
            raise BinanceDataError(
                f"Binance returned no usable progress for {venue_symbol} at {cursor.isoformat()}"
            )
        rows.extend(in_range)
        last_open = pd.Timestamp(int(in_range[-1][0]), unit="ms", tz="UTC")
        next_cursor = last_open + delta
        if next_cursor <= cursor:
            raise BinanceDataError(f"Binance pagination did not advance for {venue_symbol}")
        cursor = next_cursor

    raw = pd.DataFrame(rows, columns=["timestamp_ms", *OHLCV_COLUMNS])
    if raw.empty:
        raise BinanceDataError(f"No closed candles received for {venue_symbol}")
    duplicate_count = int(raw["timestamp_ms"].duplicated(keep=False).sum())
    if duplicate_count:
        raise BinanceDataError(f"Binance returned {duplicate_count} duplicate candle row(s) for {venue_symbol}")
    raw.sort_values("timestamp_ms", inplace=True)
    utc_open = pd.to_datetime(raw.pop("timestamp_ms"), unit="ms", utc=True)
    stored = raw.loc[:, OHLCV_COLUMNS].copy()
    stored.insert(0, "timestamp", (utc_open + STORED_UTC_OFFSET).dt.tz_localize(None))
    try:
        loaded = normalize_stored_candles(stored, timeframe=timeframe, now=server_now, strict=True)
    except CandleDataError as exc:
        raise BinanceDataError(f"Binance range incomplete for {venue_symbol}: {exc}") from exc

    expected_closes = pd.date_range(
        start=start_open + delta,
        end=end_open,
        freq=delta,
        tz="UTC",
        name="closed_at",
    )
    if not loaded.frame.index.equals(expected_closes):
        missing = expected_closes.difference(loaded.frame.index)
        raise BinanceDataError(
            f"Binance range incomplete for {venue_symbol}: expected={len(expected_closes)}, "
            f"received={len(loaded.frame)}, missing={len(missing)}"
        )
    return loaded.frame


def _load_existing(path: Path, *, now: pd.Timestamp) -> pd.DataFrame:
    if not path.is_file():
        return pd.DataFrame(
            columns=["open_at", *OHLCV_COLUMNS],
            index=pd.DatetimeIndex([], tz="UTC", name="closed_at"),
        )
    try:
        raw = pd.read_csv(path)
        _reject_conflicting_existing_duplicates(raw, path=path)
        # Non-strict normalization sorts and coalesces only duplicates already
        # proven value-identical above.  The caller then refetches from the
        # first cadence gap and performs a strict full round-trip before
        # replacing the file.
        return normalize_stored_candles(
            raw,
            timeframe="15m",
            now=now,
            strict=False,
        ).frame
    except CandleDataError as exc:
        raise BinanceDataError(f"Existing file must be repaired before reconciliation: {path}: {exc}") from exc


def _reject_conflicting_existing_duplicates(raw: pd.DataFrame, *, path: Path) -> None:
    """Reject ambiguous duplicate candles before non-strict gap repair.

    An old conflicting duplicate can sit outside the rolling refetch window.
    Silently choosing one would change the locked recursive indicator seed, so
    only value-identical duplicates may be coalesced.
    """

    required = {"timestamp", *OHLCV_COLUMNS}
    if not required.issubset(raw.columns) or raw.empty:
        return
    parsed = pd.to_datetime(raw["timestamp"], errors="coerce")
    duplicate_mask = parsed.duplicated(keep=False) & parsed.notna()
    if not bool(duplicate_mask.any()):
        return
    duplicates = raw.loc[duplicate_mask, ["timestamp", *OHLCV_COLUMNS]].copy()
    duplicates["_parsed_timestamp"] = parsed.loc[duplicate_mask].to_numpy()
    for timestamp, group in duplicates.groupby("_parsed_timestamp", sort=False):
        numeric = group.loc[:, OHLCV_COLUMNS].apply(pd.to_numeric, errors="coerce")
        if any(numeric[column].nunique(dropna=False) > 1 for column in OHLCV_COLUMNS):
            raise BinanceDataError(
                f"Existing file contains conflicting duplicate candle at "
                f"{pd.Timestamp(timestamp).isoformat()}: {path}"
            )


def _require_existing_feature_anchor(frame: pd.DataFrame, *, symbol: str) -> None:
    """Refuse a moving/truncated source that has lost the locked EMA seed."""

    anchor_open = pd.Timestamp(FEATURE_ANCHOR_M15_OPEN)
    if "open_at" not in frame.columns or not bool((frame["open_at"] == anchor_open).any()):
        raise BinanceDataError(
            f"{symbol} does not contain the locked feature-anchor candle at "
            f"{anchor_open.isoformat()}; explicit re-anchor migration required"
        )


def _first_repair_open(frame: pd.DataFrame, delta: pd.Timedelta) -> pd.Timestamp | None:
    if len(frame) < 2:
        return None
    differences = frame.index[1:] - frame.index[:-1]
    mismatches = [position for position, difference in enumerate(differences) if difference != delta]
    if not mismatches:
        return None
    # The preceding candle's close equals the first missing candle's expected
    # open, so fetching from here repairs the entire suffix deterministically.
    return frame.index[mismatches[0]]


def _atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    temp = path.with_name(f".{path.name}.tmp")
    try:
        frame.to_csv(temp, index=False)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _aware_utc(value: pd.Timestamp | str) -> pd.Timestamp:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        raise BinanceDataError("server_now must be timezone-aware")
    return timestamp.tz_convert("UTC")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Refresh and reconcile Core V2.1 Binance closed M15 candles"
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=DEFAULT_DATA_DIR,
        help="CSV directory (default: app/backtest/data)",
    )
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=None,
        help="Approved normalized symbols; default is all 24 Binance alts plus BTCUSDT",
    )
    parser.add_argument(
        "--candle-count",
        type=int,
        default=DEFAULT_RECENT_CANDLES,
        help="Recent closed M15 candles to authoritatively replace (default: 5000)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional JSON path for refresh results",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    import ccxt

    exchange = ccxt.binanceusdm({"enableRateLimit": True})
    exchange.load_markets()
    results = refresh_approved_binance_universe(
        exchange,
        data_dir=args.data_dir,
        symbols=args.symbols,
        candle_count=args.candle_count,
    )
    if args.manifest is not None:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        content = json.dumps([result.to_dict() for result in results], indent=2, sort_keys=True) + "\n"
        temp = args.manifest.with_name(f".{args.manifest.name}.tmp")
        try:
            temp.write_text(content, encoding="utf-8")
            os.replace(temp, args.manifest)
        finally:
            if temp.exists():
                temp.unlink()
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised as a CLI
    raise SystemExit(main())

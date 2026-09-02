"""Acquire and atomically persist the canonical Hyperliquid PUMP M15 file."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

import pandas as pd
import structlog

from app.backtest.core_v2_1.coverage import data_identity_for_symbol
from app.backtest.core_v2_1.data import (
    STORED_UTC_OFFSET,
    CandleDataError,
    normalize_stored_candles,
)
from app.signal.core_v2_1.market_data import (
    DEFAULT_FINALIZATION_DELAY,
    HyperliquidPublicCandleSource,
    MarketDataSourceError,
)
from app.signal.core_v2_1.models import (
    ClosedCandle,
    MarketKey,
    Venue,
    ensure_utc,
    timeframe_delta,
)
from app.trading.strategy.core_v2_1 import (
    FEATURE_ANCHOR_M15_OPEN,
    FEATURE_ANCHOR_VERSION,
    first_fully_covered_close,
)

DEFAULT_CANDLE_COUNT = 5000
DEFAULT_DATA_DIR = Path(__file__).resolve().parents[2] / "backtest" / "data"
PUMP_IDENTITY = data_identity_for_symbol("PUMP")
PUMP_FILENAME = PUMP_IDENTITY.filename
PUMP_KEY = MarketKey(
    Venue.HYPERLIQUID_PERP,
    PUMP_IDENTITY.venue_instrument,
    "15m",
)
logger = structlog.get_logger(__name__)


class HyperliquidExportError(RuntimeError):
    """PUMP history could not be proven complete and safe to replace."""


@dataclass(frozen=True)
class HyperliquidExportResult:
    strategy_symbol: str
    venue: str
    venue_instrument: str
    timeframe: str
    path: Path
    sha256: str
    row_count: int
    first_open_utc: datetime
    last_close_utc: datetime
    server_now_utc: datetime
    feature_anchor_version: str
    feature_anchor_open_utc: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy_symbol": self.strategy_symbol,
            "venue": self.venue,
            "venue_instrument": self.venue_instrument,
            "timeframe": self.timeframe,
            "path": str(self.path),
            "sha256": self.sha256,
            "row_count": self.row_count,
            "first_open_utc": self.first_open_utc.isoformat(),
            "last_close_utc": self.last_close_utc.isoformat(),
            "server_now_utc": self.server_now_utc.isoformat(),
            "feature_anchor_version": self.feature_anchor_version,
            "feature_anchor_open_utc": self.feature_anchor_open_utc.isoformat(),
        }


def load_anchored_pump_m15_seed(
    data_dir: str | Path,
    *,
    through: datetime,
) -> tuple[ClosedCandle, ...]:
    """Load a canonical PUMP CSV as exact-Decimal live-runtime seed data.

    The repository CSV stores UTC+7 wall-clock candle opens.  Validation uses
    the same strict replay contract, while candle construction reads the
    original strings so a SQLite bootstrap never round-trips prices through a
    binary float.  Venue, instrument, and timeframe provenance come from the
    locked ``PUMP_KEY`` rather than a filename-derived alias.
    """

    boundary = ensure_utc(through, field_name="through")
    path = Path(data_dir).expanduser().resolve() / PUMP_FILENAME
    try:
        raw = pd.read_csv(
            path,
            dtype={
                column: "string"
                for column in ("timestamp", "open", "high", "low", "close", "volume")
            },
        )
        normalized = normalize_stored_candles(
            raw,
            timeframe="15m",
            now=pd.Timestamp(boundary),
            strict=True,
        )
    except (FileNotFoundError, OSError, CandleDataError, ValueError) as exc:
        raise HyperliquidExportError(
            f"Canonical PUMP seed is invalid or unreadable: {path}: {exc}"
        ) from exc

    if normalized.frame.empty:
        raise HyperliquidExportError(
            f"Canonical PUMP seed has no closed candles through {boundary.isoformat()}"
        )
    if normalized.report.first_open_at != pd.Timestamp(FEATURE_ANCHOR_M15_OPEN):
        actual = (
            normalized.report.first_open_at.isoformat()
            if normalized.report.first_open_at is not None
            else "no candles"
        )
        raise HyperliquidExportError(
            "Canonical PUMP seed does not begin at the locked feature anchor: "
            f"expected {FEATURE_ANCHOR_M15_OPEN.isoformat()}, got {actual}; "
            "explicit re-anchor migration required"
        )

    duration = timeframe_delta("15m")
    closed_rows = raw.iloc[: normalized.report.output_rows]
    candles: list[ClosedCandle] = []
    try:
        for position, (_, row) in enumerate(closed_rows.iterrows()):
            stored_open = pd.Timestamp(row["timestamp"])
            if stored_open.tzinfo is not None:
                raise ValueError("stored timestamp must be timezone-naive")
            open_time = (
                stored_open - STORED_UTC_OFFSET
            ).tz_localize("UTC").to_pydatetime()
            candle = ClosedCandle(
                key=PUMP_KEY,
                open_time=open_time,
                close_time=open_time + duration,
                open=Decimal(str(row["open"])),
                high=Decimal(str(row["high"])),
                low=Decimal(str(row["low"])),
                close=Decimal(str(row["close"])),
                volume=Decimal(str(row["volume"])),
            )
            expected_close = first_fully_covered_close("15m") + duration * position
            if candle.close_time != expected_close:
                raise ValueError(
                    f"expected close {expected_close.isoformat()}, got "
                    f"{candle.close_time.isoformat()}"
                )
            candles.append(candle)
    except (InvalidOperation, TypeError, ValueError, ArithmeticError) as exc:
        raise HyperliquidExportError(
            f"Canonical PUMP seed cannot be represented exactly: {path}: {exc}"
        ) from exc

    if normalized.report.last_closed_at != pd.Timestamp(candles[-1].close_time):
        raise HyperliquidExportError(
            "Canonical PUMP seed timestamp conversion disagrees with replay validation"
        )
    return tuple(candles)


def export_latest_pump_m15(
    source: HyperliquidPublicCandleSource,
    *,
    data_dir: str | Path = DEFAULT_DATA_DIR,
    candle_count: int = DEFAULT_CANDLE_COUNT,
    server_now: datetime | None = None,
    manifest_path: str | Path | None = None,
) -> HyperliquidExportResult:
    """Extend the immutable anchored PUMP replay CSV atomically.

    A fresh file always begins at the locked feature anchor.  An existing
    anchored prefix is preserved byte-for-value and only a verified overlap
    plus new tail is fetched.  Once Hyperliquid retention no longer reaches
    the anchor, a fresh install fails instead of silently rolling the seed.
    """

    if candle_count < 1 or candle_count > DEFAULT_CANDLE_COUNT:
        raise ValueError(f"candle_count must be in [1, {DEFAULT_CANDLE_COUNT}]")
    boundary_now = ensure_utc(
        server_now or source.resolve_server_now(),
        field_name="server_now",
    )
    duration = timeframe_delta("15m")
    finalized_through = boundary_now - DEFAULT_FINALIZATION_DELAY
    last_close = _floor_boundary(finalized_through, duration)
    anchor_first_close = first_fully_covered_close("15m")
    if last_close < anchor_first_close:
        raise HyperliquidExportError(
            "Authoritative server time has not reached the locked PUMP anchor"
        )

    destination = Path(data_dir).expanduser().resolve() / PUMP_FILENAME
    existing_raw: pd.DataFrame | None = None
    existing_last_close: datetime | None = None
    if destination.exists():
        existing_raw = pd.read_csv(
            destination,
            dtype={
                column: "string"
                for column in ("open", "high", "low", "close", "volume")
            },
        )
        existing = normalize_stored_candles(
            existing_raw,
            timeframe="15m",
            now=pd.Timestamp(boundary_now),
            strict=True,
        )
        if existing.frame.empty:
            raise HyperliquidExportError("Existing PUMP file is empty and has no anchor")
        first_open = existing.report.first_open_at
        if first_open != pd.Timestamp(FEATURE_ANCHOR_M15_OPEN):
            raise HyperliquidExportError(
                "Existing PUMP file does not begin at the locked feature anchor; "
                "explicit re-anchor migration required"
            )
        assert existing.report.last_closed_at is not None
        existing_last_close = existing.report.last_closed_at.to_pydatetime()
        if existing_last_close > last_close:
            raise HyperliquidExportError(
                "Existing PUMP history extends beyond the authoritative finalized watermark"
            )
        fetch_start = existing_last_close
    else:
        fetch_start = anchor_first_close

    requested_count = int((last_close - fetch_start) / duration) + 1
    if requested_count > candle_count:
        if existing_raw is None:
            raise HyperliquidExportError(
                f"Fresh PUMP install requires {requested_count} anchored candles, "
                f"exceeding the {candle_count}-candle Hyperliquid request limit; "
                "explicit strategy-version/re-anchor migration required"
            )
        raise HyperliquidExportError(
            f"PUMP catch-up needs {requested_count} candles, exceeding the "
            f"{candle_count}-candle retention/request limit"
        )
    try:
        candles = source.fetch_closed(PUMP_KEY, fetch_start, last_close)
    except MarketDataSourceError as exc:
        raise HyperliquidExportError(
            f"Locked PUMP anchor/catch-up range is unavailable: {exc}"
        ) from exc
    _assert_exact_export_range(candles, fetch_start, last_close, duration)

    fetched_stored = pd.DataFrame(
        {
            "timestamp": [
                (pd.Timestamp(candle.open_time) + pd.Timedelta(hours=7)).tz_localize(None)
                for candle in candles
            ],
            "open": [str(candle.open) for candle in candles],
            "high": [str(candle.high) for candle in candles],
            "low": [str(candle.low) for candle in candles],
            "close": [str(candle.close) for candle in candles],
            "volume": [str(candle.volume) for candle in candles],
        }
    )
    if existing_raw is None:
        stored = fetched_stored
    else:
        _assert_immutable_overlap(existing_raw, candles[0])
        stored = pd.concat(
            (existing_raw, fetched_stored.iloc[1:]),
            ignore_index=True,
        )
    # Validate the exact in-memory representation before touching disk.
    normalized = normalize_stored_candles(
        stored,
        timeframe="15m",
        now=pd.Timestamp(boundary_now),
        strict=True,
    )
    expected_total = int((last_close - anchor_first_close) / duration) + 1
    if len(normalized.frame) != expected_total:
        raise HyperliquidExportError(
            "Strict validation did not preserve the exact anchored candle range"
        )
    if normalized.report.first_open_at != pd.Timestamp(FEATURE_ANCHOR_M15_OPEN):
        raise HyperliquidExportError("Serialized PUMP data lost the locked feature anchor")
    if normalized.report.last_closed_at != pd.Timestamp(last_close):
        raise HyperliquidExportError("Serialized PUMP data has an incomplete latest tail")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_name(f".{destination.name}.tmp")
    try:
        stored.to_csv(temp, index=False)
        # Round-trip the serialized bytes through the replay loader contract.
        round_trip_raw = pd.read_csv(temp)
        round_trip = normalize_stored_candles(
            round_trip_raw,
            timeframe="15m",
            now=pd.Timestamp(boundary_now),
            strict=True,
        )
        if not round_trip.frame.index.equals(normalized.frame.index):
            raise HyperliquidExportError("CSV round-trip changed candle timestamps")
        columns = ["open", "high", "low", "close", "volume"]
        if not round_trip.frame.loc[:, columns].equals(
            normalized.frame.loc[:, columns]
        ):
            raise HyperliquidExportError("CSV round-trip changed OHLCV values")
        digest = hashlib.sha256(temp.read_bytes()).hexdigest()
        os.replace(temp, destination)
    finally:
        if temp.exists():
            temp.unlink()

    result = HyperliquidExportResult(
        strategy_symbol="PUMP",
        venue=Venue.HYPERLIQUID_PERP.value,
        venue_instrument=PUMP_KEY.instrument,
        timeframe="15m",
        path=destination,
        sha256=digest,
        row_count=len(stored),
        first_open_utc=FEATURE_ANCHOR_M15_OPEN,
        last_close_utc=last_close,
        server_now_utc=boundary_now,
        feature_anchor_version=FEATURE_ANCHOR_VERSION,
        feature_anchor_open_utc=FEATURE_ANCHOR_M15_OPEN,
    )
    if manifest_path is not None:
        _atomic_json(Path(manifest_path).expanduser().resolve(), result.to_dict())
    return result


def _assert_exact_export_range(
    candles,
    expected_start: datetime,
    expected_end: datetime,
    duration: timedelta,
) -> None:
    expected_count = int((expected_end - expected_start) / duration) + 1
    if len(candles) != expected_count:
        raise HyperliquidExportError(
            f"Expected {expected_count} closed PUMP candles, received {len(candles)}"
        )
    for index, candle in enumerate(candles):
        expected_close = expected_start + duration * index
        if candle.key != PUMP_KEY or candle.close_time != expected_close:
            raise HyperliquidExportError(
                "Hyperliquid response does not cover the exact requested "
                f"closed-candle range at {expected_close.isoformat()}"
            )


def _assert_immutable_overlap(existing_raw: pd.DataFrame, overlap) -> None:
    if existing_raw.empty:
        raise HyperliquidExportError("Existing PUMP file is empty")
    row = existing_raw.iloc[-1]
    expected_timestamp = (
        pd.Timestamp(overlap.open_time) + pd.Timedelta(hours=7)
    ).tz_localize(None)
    if pd.Timestamp(row["timestamp"]) != expected_timestamp:
        raise HyperliquidExportError("Existing PUMP overlap timestamp changed")
    expected = {
        "open": overlap.open,
        "high": overlap.high,
        "low": overlap.low,
        "close": overlap.close,
        "volume": overlap.volume,
    }
    for column, value in expected.items():
        if Decimal(str(row[column])) != value:
            raise HyperliquidExportError(
                f"Hyperliquid rewrote immutable PUMP {column} at "
                f"{overlap.close_time.isoformat()}"
            )


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    try:
        temp.write_text(
            json.dumps(payload, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def _floor_boundary(value: datetime, duration: timedelta) -> datetime:
    seconds = int(duration.total_seconds())
    epoch_seconds = int(ensure_utc(value, field_name="boundary").timestamp())
    return datetime.fromtimestamp((epoch_seconds // seconds) * seconds, tz=UTC)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fetch the latest fully closed Hyperliquid PUMP M15 candles"
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--candle-count", type=int, default=DEFAULT_CANDLE_COUNT)
    parser.add_argument("--manifest", type=Path, default=None)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    result = export_latest_pump_m15(
        HyperliquidPublicCandleSource(),
        data_dir=args.data_dir,
        candle_count=args.candle_count,
        manifest_path=args.manifest,
    )
    logger.info("core_v2_hyperliquid_export_complete", **result.to_dict())
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI boundary
    raise SystemExit(main())

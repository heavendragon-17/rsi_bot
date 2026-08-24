"""Core V2.1 universe coverage discovery and metadata export."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from app.backtest.core_v2_1.data import CandleDataError, load_stored_candles
from app.trading.strategy.core_v2_1.config import (
    BENCHMARK_SYMBOL,
    HYPERLIQUID_TRADE_CANDIDATES,
    TRADE_CANDIDATES,
    instrument_for_symbol,
)
from app.trading.strategy.core_v2_1.feature_anchor import FEATURE_ANCHOR_M15_OPEN

# Locked, reviewer-approved Core V2.1 universe.  Order is intentional and is
# retained in coverage reports and deterministic same-timestamp replay ties.
CORE_V2_1_UNIVERSE: tuple[str, ...] = TRADE_CANDIDATES
BINANCE_BENCHMARK = BENCHMARK_SYMBOL
HYPERLIQUID_SYMBOLS = frozenset(HYPERLIQUID_TRADE_CANDIDATES)
EXPECTED_LOCAL_SIX: tuple[str, ...] = (
    "ETHUSDT",
    "SOLUSDT",
    "BNBUSDT",
    "XRPUSDT",
    "LINKUSDT",
    "HYPEUSDT",
)

# The locked V2.1 feature anchor was acquired as 5,000 M15 candles per
# market.  A shorter file is not sufficient evidence for the standardized
# replay/runtime seed contract, even when its CSV schema is otherwise valid.
MINIMUM_CORE_V2_1_M15_ROWS = 5_000


def _require_complete_feature_anchor(frame: pd.DataFrame, *, symbol: str) -> None:
    """Prove that the immutable indicator seed window is present in ``frame``."""

    anchor_open = pd.Timestamp(FEATURE_ANCHOR_M15_OPEN)
    anchored = frame.loc[frame["open_at"] >= anchor_open]
    if anchored.empty or pd.Timestamp(anchored.iloc[0]["open_at"]) != anchor_open:
        actual = "no candle" if anchored.empty else pd.Timestamp(
            anchored.iloc[0]["open_at"]
        ).isoformat()
        raise CandleDataError(
            f"{symbol} feature anchor is incomplete: expected open "
            f"{anchor_open.isoformat()}, got {actual}"
        )
    if len(anchored) < MINIMUM_CORE_V2_1_M15_ROWS:
        raise CandleDataError(
            f"{symbol} has {len(anchored)} M15 rows at or after the locked "
            f"feature anchor; Core V2.1 requires at least "
            f"{MINIMUM_CORE_V2_1_M15_ROWS}"
        )


def venue_for_symbol(symbol: str) -> str:
    """Return the approved data venue for a normalized Core V2.1 symbol."""

    normalized = normalize_symbol(symbol)
    if normalized == BINANCE_BENCHMARK:
        return "BINANCE_FUTURES"
    return instrument_for_symbol(normalized).venue.value


def normalize_symbol(symbol: str) -> str:
    return symbol.upper().replace("/", "").replace(":", "")


@dataclass(frozen=True)
class DataIdentity:
    """Structural identity that prevents cross-venue ticker substitution."""

    strategy_symbol: str
    venue: str
    venue_instrument: str
    timeframe: str
    filename: str


def data_identity_for_symbol(symbol: str, *, timeframe: str = "15m") -> DataIdentity:
    normalized = normalize_symbol(symbol)
    if normalized == "PUMP":
        spec = instrument_for_symbol(normalized)
        return DataIdentity(
            strategy_symbol="PUMP",
            venue=spec.venue.value,
            venue_instrument=spec.venue_symbol,
            timeframe=timeframe,
            filename=f"HYPERLIQUID__PUMP_USDC_PERP_{timeframe}.csv",
        )
    if normalized not in {*CORE_V2_1_UNIVERSE, BINANCE_BENCHMARK}:
        raise CandleDataError(f"Unknown Core V2.1 data identity: {symbol!r}")
    if not normalized.endswith("USDT"):
        raise CandleDataError(f"Unsupported Binance quote asset for {normalized}")
    base = normalized[: -len("USDT")]
    venue_instrument = (
        instrument_for_symbol(normalized).venue_symbol
        if normalized != BINANCE_BENCHMARK
        else f"{base}/USDT:USDT"
    )
    return DataIdentity(
        strategy_symbol=normalized,
        venue="BINANCE_FUTURES",
        venue_instrument=venue_instrument,
        timeframe=timeframe,
        filename=f"{normalized}_{timeframe}.csv",
    )


def data_path_for_symbol(data_dir: str | Path, symbol: str, *, timeframe: str = "15m") -> Path:
    return Path(data_dir) / data_identity_for_symbol(symbol, timeframe=timeframe).filename


@dataclass(frozen=True)
class CoverageFile:
    symbol: str
    venue: str
    venue_instrument: str
    path: str
    present: bool
    rows: int | None
    first_open_at: str | None
    last_closed_at: str | None
    valid: bool | None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "venue": self.venue,
            "venue_instrument": self.venue_instrument,
            "path": self.path,
            "present": self.present,
            "rows": self.rows,
            "first_open_at": self.first_open_at,
            "last_closed_at": self.last_closed_at,
            "valid": self.valid,
            "error": self.error,
        }


@dataclass(frozen=True)
class CoverageReport:
    data_dir: str
    timeframe: str
    required_count: int
    available_symbols: tuple[str, ...]
    missing_symbols: tuple[str, ...]
    invalid_symbols: tuple[str, ...]
    benchmark_available: bool
    benchmark_valid: bool | None
    benchmark_rows: int | None
    benchmark_first_open_at: str | None
    benchmark_last_closed_at: str | None
    benchmark_error: str | None
    synthetic_btc_fixture_present: bool
    common_first_open_at: str | None
    common_last_closed_at: str | None
    files: tuple[CoverageFile, ...]

    @property
    def available_count(self) -> int:
        return len(self.available_symbols)

    @property
    def is_complete(self) -> bool:
        benchmark_ok = self.benchmark_available and (
            self.benchmark_valid is not False
        )
        return not self.missing_symbols and not self.invalid_symbols and benchmark_ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "data_dir": self.data_dir,
            "timeframe": self.timeframe,
            "required_count": self.required_count,
            "available_count": self.available_count,
            "available_symbols": list(self.available_symbols),
            "missing_symbols": list(self.missing_symbols),
            "invalid_symbols": list(self.invalid_symbols),
            "benchmark": {
                "symbol": BINANCE_BENCHMARK,
                "available": self.benchmark_available,
                "valid": self.benchmark_valid,
                "rows": self.benchmark_rows,
                "first_open_at": self.benchmark_first_open_at,
                "last_closed_at": self.benchmark_last_closed_at,
                "error": self.benchmark_error,
                "synthetic_fixture_present": self.synthetic_btc_fixture_present,
            },
            "common_first_open_at": self.common_first_open_at,
            "common_last_closed_at": self.common_last_closed_at,
            "complete": self.is_complete,
            "files": [item.to_dict() for item in self.files],
        }


def scan_local_coverage(
    data_dir: str | Path,
    *,
    validate: bool = False,
    now: pd.Timestamp | str | None = None,
) -> CoverageReport:
    """Discover approved M15 files and optionally validate their contents.

    Filename discovery is enough to identify the current 6/25 footprint and is
    intentionally cheap.  ``validate=True`` adds cadence/OHLC checks and a
    common point-in-time window to the report.
    """

    root = Path(data_dir).resolve()
    available: list[str] = []
    missing: list[str] = []
    invalid: list[str] = []
    files: list[CoverageFile] = []
    first_opens: list[pd.Timestamp] = []
    last_closes: list[pd.Timestamp] = []

    for symbol in CORE_V2_1_UNIVERSE:
        identity = data_identity_for_symbol(symbol)
        path = root / identity.filename
        if not path.is_file():
            missing.append(symbol)
            files.append(
                CoverageFile(
                    symbol=symbol,
                    venue=identity.venue,
                    venue_instrument=identity.venue_instrument,
                    path=str(path),
                    present=False,
                    rows=None,
                    first_open_at=None,
                    last_closed_at=None,
                    valid=None,
                )
            )
            continue
        available.append(symbol)
        if not validate:
            files.append(
                CoverageFile(
                    symbol=symbol,
                    venue=identity.venue,
                    venue_instrument=identity.venue_instrument,
                    path=str(path),
                    present=True,
                    rows=None,
                    first_open_at=None,
                    last_closed_at=None,
                    valid=None,
                )
            )
            continue
        try:
            loaded = load_stored_candles(path, timeframe="15m", now=now, strict=True)
            report = loaded.report
            _require_complete_feature_anchor(loaded.frame, symbol=symbol)
            if report.first_open_at is not None:
                first_opens.append(report.first_open_at)
            if report.last_closed_at is not None:
                last_closes.append(report.last_closed_at)
            files.append(
                CoverageFile(
                    symbol=symbol,
                    venue=identity.venue,
                    venue_instrument=identity.venue_instrument,
                    path=str(path),
                    present=True,
                    rows=report.output_rows,
                    first_open_at=_iso(report.first_open_at),
                    last_closed_at=_iso(report.last_closed_at),
                    valid=True,
                )
            )
        except (CandleDataError, OSError, ValueError) as exc:
            invalid.append(symbol)
            files.append(
                CoverageFile(
                    symbol=symbol,
                    venue=identity.venue,
                    venue_instrument=identity.venue_instrument,
                    path=str(path),
                    present=True,
                    rows=None,
                    first_open_at=None,
                    last_closed_at=None,
                    valid=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )

    benchmark_path = data_path_for_symbol(root, BINANCE_BENCHMARK)
    benchmark_available = benchmark_path.is_file()
    benchmark_valid: bool | None = None
    benchmark_rows: int | None = None
    benchmark_first_open_at: str | None = None
    benchmark_last_closed_at: str | None = None
    benchmark_error: str | None = None
    if validate and benchmark_available:
        try:
            benchmark_loaded = load_stored_candles(
                benchmark_path,
                timeframe="15m",
                now=now,
                strict=True,
            )
            benchmark_report = benchmark_loaded.report
            _require_complete_feature_anchor(
                benchmark_loaded.frame,
                symbol=BINANCE_BENCHMARK,
            )
            benchmark_valid = True
            benchmark_rows = benchmark_report.output_rows
            benchmark_first_open_at = _iso(benchmark_report.first_open_at)
            benchmark_last_closed_at = _iso(benchmark_report.last_closed_at)
            if benchmark_report.first_open_at is not None:
                first_opens.append(benchmark_report.first_open_at)
            if benchmark_report.last_closed_at is not None:
                last_closes.append(benchmark_report.last_closed_at)
        except (CandleDataError, OSError, ValueError) as exc:
            benchmark_valid = False
            benchmark_error = f"{type(exc).__name__}: {exc}"
    elif validate:
        benchmark_valid = False
        benchmark_error = f"Missing benchmark file: {benchmark_path}"
    synthetic_fixture = root / "BTC_USDT_15m.csv"
    common_first = max(first_opens) if validate and first_opens else None
    common_last = min(last_closes) if validate and last_closes else None
    return CoverageReport(
        data_dir=str(root),
        timeframe="15m",
        required_count=len(CORE_V2_1_UNIVERSE),
        available_symbols=tuple(available),
        missing_symbols=tuple(missing),
        invalid_symbols=tuple(invalid),
        benchmark_available=benchmark_available,
        benchmark_valid=benchmark_valid,
        benchmark_rows=benchmark_rows,
        benchmark_first_open_at=benchmark_first_open_at,
        benchmark_last_closed_at=benchmark_last_closed_at,
        benchmark_error=benchmark_error,
        synthetic_btc_fixture_present=synthetic_fixture.is_file(),
        common_first_open_at=_iso(common_first),
        common_last_closed_at=_iso(common_last),
        files=tuple(files),
    )


def assert_pre_download_local_six(report: CoverageReport) -> None:
    """Verify the pre-acquisition data footprint is the audited 6/25 subset.

    This is a migration/preflight assertion, not a permanent production
    invariant: task 5 intentionally grows coverage beyond six symbols.
    """

    if report.available_symbols != EXPECTED_LOCAL_SIX:
        raise CandleDataError(
            "Local Core V2.1 coverage changed: expected "
            f"{EXPECTED_LOCAL_SIX!r}, found {report.available_symbols!r}"
        )


def _iso(value: pd.Timestamp | None) -> str | None:
    return value.isoformat() if value is not None else None

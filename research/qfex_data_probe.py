"""QFEX equity data probe (research-only, read-only infrastructure reuse).

Milestone: fetch ONE QFEX equity instrument's historical candles and
demonstrate that its instrument candles load through the EXISTING backtest
data reader. No strategy, no bot, no production changes.

Existing loader reused (read-only, not modified):
    app.backtest.signal_replay_data.load_ohlcv_csv
Schema: timestamp,open,high,low,close,volume. Naive timestamps are
interpreted as UTC+7 storage time; timezone-aware timestamps are converted
to UTC. The probe writes timezone-aware UTC timestamps so the loader sees
the exact canonical instants (conversion documented in the report).

Official QFEX docs followed (verified 2026-09-20, no guessing):
    https://docs.qfex.com/api-reference/rest/market-data/underlier-historic
    https://docs.qfex.com/api-reference/rest/market-data/candles
    https://docs.qfex.com/api-reference/enums.md  (CandlesInterval wire values)
Base URL: https://api.qfex.com (per docs OpenAPI `servers` + md pages).
    GET /refdata
    GET /underlier/{symbol}?interval&fromISO&toISO
    GET /candles/{symbol}?resolution&fromISO&toISO
15-minute wire values: underlier ``interval=15m`` (verified live);
instrument ``resolution=15MINS`` (per Enums CandlesInterval table; ``15m``
is rejected with 400 "unsupported resolution"). No numeric REST rate limit
is stated in the Introduction/Enums docs; the probe stays minimal (3
sequential requests, 20 s timeout each, no retries).

Budget: 1 symbol, 1 timeframe, 1 seven-day window, <=8 market-data
requests. This script makes exactly 3: refdata + underlier + candles.

Usage:
    C:/Python314/python.exe research/qfex_data_probe.py \
        --out research/results/qfex_data_probe/<run-id>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

# Allow `research/qfex_data_probe.py` direct execution: repo root on sys.path
# (same pattern as app/backtest/backtest.py) so the EXISTING backtest data
# reader (`app.backtest.signal_replay_data`) is importable for the loader demo.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import structlog

logger = structlog.get_logger()

BASE_URL = "https://api.qfex.com"
REQUEST_TIMEOUT_S = 20
MAX_MARKET_DATA_REQUESTS = 8
USER_AGENT = "rsi-bot-qfex-probe/1.0"

UNDERLIER_INTERVAL = "15m"  # verified live against /underlier/{symbol}
CANDLES_RESOLUTION = "15MINS"  # CandlesInterval wire value per docs enums.md
STEP_MINUTES = 15
WINDOW_DAYS = 7

LOADER_TIMEFRAME_LABEL = "15m"  # valid key of TRIGGER_DURATION_BY_TIMEFRAME


# ---------------------------------------------------------------------------
# HTTP (single attempt per request, no retries per assignment budget)
# ---------------------------------------------------------------------------

def http_get_json(url: str, params: dict[str, str]) -> tuple[int, bytes, float, str]:
    """One GET with a 20 s timeout. Returns (status, raw_body, elapsed_ms, url)."""
    final_url = url + "?" + urllib.parse.urlencode(params) if params else url
    request = urllib.request.Request(
        final_url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}
    )
    started = time.perf_counter()
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_S) as response:
        body = response.read()
        status = int(response.status)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return status, body, elapsed_ms, final_url


def sha256_hex(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Window + instrument selection (recorded before any price fetch)
# ---------------------------------------------------------------------------

def seven_completed_utc_days(now_utc: datetime) -> tuple[datetime, datetime]:
    """Last seven *completed* UTC days: [end-7d, end), end = today 00:00 UTC."""
    end = now_utc.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return end - timedelta(days=WINDOW_DAYS), end


def to_iso_z(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def select_instrument(refdata: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pick the first ACTIVE EQUITY instrument in refdata response order.

    Deterministic and chart-blind: no price data is consulted. Returns
    (record, selection_receipt) where the receipt records the choice.
    """
    rows = refdata.get("data", [])
    counts: dict[str, int] = {}
    for row in rows:
        key = f"{row.get('product_category')}/{row.get('status')}"
        counts[key] = counts.get(key, 0) + 1
    for index, row in enumerate(rows):
        if row.get("product_category") == "EQUITY" and row.get("status") == "ACTIVE":
            receipt = {
                "rule": "first ACTIVE EQUITY instrument in /refdata response order, chart-blind (no price data consulted); single-stock preferred and satisfied by the first match",
                "symbol": row.get("symbol"),
                "base_asset": row.get("base_asset"),
                "quote_asset": row.get("quote_asset"),
                "response_index": index,
                "response_total": len(rows),
                "category_status_counts": counts,
            }
            return row, receipt
    raise ValueError("No ACTIVE EQUITY instrument in refdata response")


# ---------------------------------------------------------------------------
# Normalization (pure functions; covered by fixture tests, no live calls)
# ---------------------------------------------------------------------------

def _parse_utc_instant(raw: str) -> datetime:
    """Parse an ISO instant to tz-aware UTC. Naive values are rejected."""
    text = str(raw).strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError(f"Naive timestamp without timezone: {raw!r}")
    return parsed.astimezone(UTC)


def format_canonical_utc(value: datetime) -> str:
    """Canonical storage form: tz-aware UTC (loader converts these to UTC exactly).

    Sub-second precision is preserved when present so distinct fractional
    instants can never collide into duplicate timestamps.
    """
    moment = value.astimezone(UTC)
    base = moment.strftime("%Y-%m-%d %H:%M:%S")
    if moment.microsecond:
        base += f".{moment.microsecond:06d}"
    return base + "+00:00"


def normalize_underlier(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize underlier OHLC points. No volume exists upstream: none is added."""
    rows: list[dict[str, Any]] = []
    for position, point in enumerate(points):
        for field in ("windowStart", "openPrice", "highPrice", "lowPrice", "closePrice"):
            if field not in point or point[field] is None:
                raise ValueError(f"Underlier point {position} missing required field {field!r}")
        instant = _parse_utc_instant(point["windowStart"])
        try:
            open_ = float(point["openPrice"])
            high = float(point["highPrice"])
            low = float(point["lowPrice"])
            close = float(point["closePrice"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Underlier point {position} has non-numeric OHLC: {exc}") from exc
        rows.append(
            {
                "timestamp": format_canonical_utc(instant),
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "symbol": point.get("symbol"),
                "interval": point.get("interval"),
                "windowStart": point["windowStart"],
            }
        )
    rows.sort(key=lambda row: _parse_utc_instant(row["timestamp"]))
    return rows


def normalize_candles(candles: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Normalize instrument candles.

    Returns (loader_rows, full_rows). loader_rows fit the existing loader
    schema (timestamp,open,high,low,close,volume) with volume := QFEX
    ``usdVolume`` (quote-notional, venue-reported; documented, not invented).
    full_rows additionally retain baseTokenVolume, trades (nullable),
    orderbookMidPriceOpen/Close, startingOpenInterest, resolution, ticker.
    """
    loader_rows: list[dict[str, Any]] = []
    full_rows: list[dict[str, Any]] = []
    for position, candle in enumerate(candles):
        for field in ("startedAt", "open", "high", "low", "close", "usdVolume", "baseTokenVolume"):
            if field not in candle or candle[field] is None:
                raise ValueError(f"Candle {position} missing required field {field!r}")
        instant = _parse_utc_instant(candle["startedAt"])
        try:
            open_ = float(candle["open"])
            high = float(candle["high"])
            low = float(candle["low"])
            close = float(candle["close"])
            volume_usd = float(candle["usdVolume"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Candle {position} has non-numeric OHLC/volume: {exc}") from exc
        timestamp = format_canonical_utc(instant)
        loader_rows.append(
            {
                "timestamp": timestamp,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume_usd,
            }
        )
        full_rows.append(
            {
                "timestamp": timestamp,
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume_usd": volume_usd,
                "volume_base": candle["baseTokenVolume"],
                "trades": candle.get("trades"),
                "mid_open": candle.get("orderbookMidPriceOpen"),
                "mid_close": candle.get("orderbookMidPriceClose"),
                "startingOpenInterest": candle.get("startingOpenInterest"),
                "resolution": candle.get("resolution"),
                "ticker": candle.get("ticker"),
                "startedAt": candle["startedAt"],
            }
        )
    loader_rows.sort(key=lambda row: _parse_utc_instant(row["timestamp"]))
    full_rows.sort(key=lambda row: _parse_utc_instant(row["timestamp"]))
    return loader_rows, full_rows


def close_divergence_stats(
    underlier_rows: list[dict[str, Any]], full_rows: list[dict[str, Any]]
) -> dict[str, Any]:
    """Observed absolute close difference on common intervals (no quality verdict).

    Purely descriptive: reference vs traded-instrument closes need not match
    tick-for-tick; this quantifies what the chart shows without classifying
    any deviation as an error.
    """
    from collections import defaultdict

    instrument_legs: dict[str, list[float]] = defaultdict(list)
    for row in full_rows:
        instrument_legs[row["timestamp"]].append(float(row["close"]))
    # Pairwise: every underlier leg is compared against every instrument leg
    # on the same stamp, so duplicate timestamps never collapse silently.
    diffs = [
        (row["timestamp"], abs(float(row["close"]) - leg))
        for row in underlier_rows
        for leg in instrument_legs.get(row["timestamp"], [])
    ]
    if not diffs:
        return {"common_intervals": 0, "max_abs_diff": None, "max_at": None, "mean_abs_diff": None}
    peak = max(diffs, key=lambda item: item[1])
    return {
        "common_intervals": len(diffs),
        "comparison": "pairwise legs per shared timestamp (duplicate stamps expand, never collapse)",
        "max_abs_diff": round(peak[1], 6),
        "max_at": peak[0].replace(" ", "T").replace("+00:00", "Z"),
        "mean_abs_diff": round(sum(value for _, value in diffs) / len(diffs), 6),
    }


def ohlc_violations(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Flag rows where high/low contradict the OHLC body (or values are bad)."""
    findings: list[dict[str, Any]] = []
    for position, row in enumerate(rows):
        try:
            o, h, low, c = (float(row[k]) for k in ("open", "high", "low", "close"))
        except (TypeError, ValueError):
            findings.append({"position": position, "timestamp": row.get("timestamp"), "issue": "non-numeric OHLC"})
            continue
        if not all(v == v and v not in (float("inf"), float("-inf")) for v in (o, h, low, c)):
            findings.append({"position": position, "timestamp": row.get("timestamp"), "issue": "non-finite OHLC"})
            continue
        if h < max(o, low, c) or low > min(o, h, c):
            findings.append(
                {
                    "position": position,
                    "timestamp": row.get("timestamp"),
                    "issue": f"high/low inconsistent with body (O={o} H={h} L={low} C={c})",
                }
            )
    return findings


def instrument_field_quality(full_rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Describe upstream sentinel/nullable instrument fields, verbatim.

    Venue sentinel values (e.g. "0" midpoints/open-interest, null trades)
    are retained as returned and flagged here so they are never mistaken
    for measurements or used as signal.
    """
    total = len(full_rows)

    def is_zero(value: Any) -> bool:
        try:
            return float(value) == 0.0  # noqa: PLR2004
        except (TypeError, ValueError):
            return False

    quality = {
        "rows": total,
        "trades_null": sum(1 for row in full_rows if row.get("trades") is None),
        "zero_volume_usd": sum(1 for row in full_rows if is_zero(row.get("volume_usd"))),
    }
    for field in ("volume_base", "mid_open", "mid_close", "startingOpenInterest"):
        quality[f"zero_{field}"] = sum(1 for row in full_rows if is_zero(row.get(field)))
    quality["note"] = (
        "Sentinel/nullable fields are retained verbatim from the venue response; "
        "zero/null legs are not measurements and must not feed signal logic."
    )
    return quality


def coverage_summary(
    rows: list[dict[str, Any]], start: datetime, end: datetime, step_minutes: int = STEP_MINUTES
) -> dict[str, Any]:
    """Coverage over the expected 15-min grid. Gaps are reported as-is.

    Missing intervals are NOT classified as corruption: equities do not
    trade around the clock, so session gaps are expected in this sample.
    """
    import pandas as pd

    stamps = [_parse_utc_instant(row["timestamp"]) for row in rows]
    expected = start
    grid: list[datetime] = []
    while expected < end:
        grid.append(expected)
        expected += timedelta(minutes=step_minutes)
    grid_set = set(grid)
    actual_set = set(stamps)
    missing = sorted(grid_set - actual_set)
    extra = sorted(actual_set - grid_set)
    seen: set[datetime] = set()
    duplicates = 0
    for stamp in stamps:
        if stamp in seen:
            duplicates += 1
        else:
            seen.add(stamp)
    null_fields = ("open", "high", "low", "close", "volume")
    nulls = sum(
        1
        for row in rows
        for key in null_fields
        if key in row and (row.get(key) is None or (isinstance(row.get(key), float) and pd.isna(row.get(key))))
    )
    return {
        "rows": len(rows),
        "expected_intervals": len(grid),
        "present_intervals": len(actual_set & grid_set),
        "missing_intervals": len(missing),
        "missing_list": [stamp.strftime("%Y-%m-%dT%H:%M:%SZ") for stamp in missing[:72]],
        "missing_truncated": len(missing) > 72,
        "extra_intervals": len(extra),
        "extra_list": [stamp.strftime("%Y-%m-%dT%H:%M:%SZ") for stamp in extra[:72]],
        "extra_truncated": len(extra) > 72,
        "duplicates": duplicates,
        "nulls_ohlc_volume": nulls,
        "first_timestamp": min(stamps).strftime("%Y-%m-%dT%H:%M:%SZ") if stamps else None,
        "last_timestamp": max(stamps).strftime("%Y-%m-%dT%H:%M:%SZ") if stamps else None,
        "ohlc_violations": ohlc_violations(rows),
        "session_note": (
            "Missing intervals are reported as observed gaps only; "
            "non-trading-session gaps are not classified as corruption, and this "
            "7-day sample does not establish the API's full historical coverage."
        ),
    }


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

def write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    import csv

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def render_close_chart(
    path: Path,
    underlier_rows: list[dict[str, Any]],
    full_rows: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    symbol: str,
) -> None:
    """One figure comparing underlier vs instrument closes on the full grid.

    Both series are reindexed to the complete 15-minute grid; absent
    intervals stay NaN so gaps render as visible breaks (never connected).
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import pandas as pd

    grid = pd.date_range(start=start, end=end, freq="15min", inclusive="left", tz=UTC)
    under = pd.Series(
        {row["timestamp"]: row["close"] for row in underlier_rows},
    )
    under.index = pd.to_datetime(under.index, utc=True)
    inst = pd.Series({row["timestamp"]: row["close"] for row in full_rows})
    inst.index = pd.to_datetime(inst.index, utc=True)
    under = under.reindex(grid)
    inst = inst.reindex(grid)

    figure, axis = plt.subplots(figsize=(12, 5))
    axis.plot(grid, under.values, label="underlier close (QFEX index/reference)", linewidth=1.2)
    axis.plot(grid, inst.values, label="instrument close (traded NVDA-USD)", linewidth=1.2, alpha=0.85)
    axis.set_title(f"{symbol} 15m closes — underlier vs instrument (gaps = missing intervals, left visible)")
    axis.set_xlabel("UTC")
    axis.set_ylabel("USD")
    axis.legend(loc="best")
    figure.autofmt_xdate()
    figure.tight_layout()
    figure.savefig(path, dpi=110)
    plt.close(figure)


def demonstrate_loader(loader_csv: Path) -> dict[str, Any]:
    """Call the EXISTING backtest data reader on the instrument loader CSV.

    No strategy is started; this only proves the venue-normalized file
    flows through the repository's own reader.
    """
    from app.backtest.signal_replay_data import REQUIRED_COLUMNS, load_ohlcv_csv

    frame = load_ohlcv_csv(loader_csv, LOADER_TIMEFRAME_LABEL)
    return {
        "loader": "app.backtest.signal_replay_data.load_ohlcv_csv",
        "required_columns": list(REQUIRED_COLUMNS),
        "timeframe_label": LOADER_TIMEFRAME_LABEL,
        "rows": int(len(frame)),
        "first_utc": frame.index.min().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "last_utc": frame.index.max().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "columns": list(frame.columns),
        "timestamp_convention": (
            "Loader parses timestamps with pandas mixed-format; naive values are "
            "assumed UTC+7 storage time, tz-aware values convert to UTC. The probe "
            "writes tz-aware '+00:00' UTC stamps, so the loader resolves the exact "
            "canonical instants with no shift. BacktestEngine reads the same "
            "timestamp,open,high,low,close,volume columns via pd.read_csv "
            "(app/backtest/engine/backtest_engine.py:55) + pd.to_datetime (:76)."
        ),
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _finalize(
    out_dir: Path,
    raw_refdata: bytes,
    raw_underlier: bytes,
    raw_candles: bytes,
    requests_log: list[dict[str, Any]],
    start: datetime,
    end: datetime,
    from_iso: str,
    to_iso: str,
    symbol_override: str | None,
    run_utc: datetime,
    budget_used: int | None = None,
) -> dict[str, Any]:
    """Shared finalize path: normalize saved raw bytes, verify loader, write artifacts.

    Used by live runs and by offline reruns from preserved raw responses, so
    both produce identical artifacts from identical inputs without extra requests.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw_refdata.json").write_bytes(raw_refdata)
    (out_dir / "raw_underlier.json").write_bytes(raw_underlier)
    (out_dir / "raw_candles.json").write_bytes(raw_candles)

    if symbol_override:
        symbol = symbol_override
        total = len(json.loads(raw_refdata.decode("utf-8")).get("data", []))
        receipt = {"rule": "pinned override --symbol", "symbol": symbol, "response_index": None,
                   "response_total": total, "base_asset": symbol.split("-")[0],
                   "quote_asset": symbol.split("-")[-1], "category_status_counts": {}}
    else:
        record, receipt = select_instrument(json.loads(raw_refdata.decode("utf-8")))
        symbol = str(record["symbol"])
    receipt["window"] = {"fromISO": from_iso, "toISO": to_iso, "timeframe": "15-minute"}
    receipt["wire_values"] = {"underlier_interval": UNDERLIER_INTERVAL, "candles_resolution": CANDLES_RESOLUTION}
    logger.info("qfex_instrument_selected", symbol=receipt.get("symbol"),
                response_index=receipt.get("response_index"), response_total=receipt.get("response_total"))

    underlier_rows = normalize_underlier(json.loads(raw_underlier.decode("utf-8")).get("data", []))
    loader_rows, full_rows = normalize_candles(json.loads(raw_candles.decode("utf-8")).get("candles", []))

    # Normalized artifacts (raw responses preserved above, untouched).
    write_csv(out_dir / "normalized_underlier.csv",
              ["timestamp", "open", "high", "low", "close", "symbol", "interval", "windowStart"], underlier_rows)
    write_csv(out_dir / "normalized_instrument_full.csv",
              ["timestamp", "open", "high", "low", "close", "volume_usd", "volume_base", "trades",
               "mid_open", "mid_close", "startingOpenInterest", "resolution", "ticker", "startedAt"], full_rows)
    loader_csv = out_dir / "loader_instrument_15m.csv"
    write_csv(loader_csv, ["timestamp", "open", "high", "low", "close", "volume"], loader_rows)

    # Coverage + loader demonstration (no strategy, no bot).
    coverage = {
        "symbol": symbol,
        "venue": "QFEX",
        "timeframe": "15-minute",
        "window": {"fromISO": from_iso, "toISO": to_iso},
        "underlier": coverage_summary(underlier_rows, start, end),
        "instrument": coverage_summary(
            [{"timestamp": r["timestamp"], "open": r["open"], "high": r["high"], "low": r["low"], "close": r["close"]}
             for r in full_rows], start, end),
        "volume_note": (
            "Underlier responses carry no volume/trade fields, so none is stored for underlier. "
            "Instrument loader `volume` := venue `usdVolume` (quote-notional); `baseTokenVolume`, "
            "`trades` (nullable), midpoint open/close and startingOpenInterest are retained in "
            "normalized_instrument_full.csv. No volume invented, no underlier-for-instrument "
            "substitution, no gap filling."
        ),
        "close_divergence": close_divergence_stats(underlier_rows, full_rows),
        "field_quality": instrument_field_quality(full_rows),
    }
    loader_result = demonstrate_loader(loader_csv)

    render_close_chart(out_dir / "chart_underlier_vs_instrument_close.png", underlier_rows, full_rows, start, end, symbol)

    used = len(requests_log) if budget_used is None else budget_used
    live_repro = (
        f"C:/Python314/python.exe research/qfex_data_probe.py --out {out_dir.as_posix()} "
        f"--from-iso {from_iso} --to-iso {to_iso} --symbol {symbol}"
    )
    reproduction = (
        f"{live_repro}  # live (spends 3 requests) OR offline with 0 new requests: "
        f"{live_repro} --raw-dir {out_dir.as_posix()}"
    )
    metadata = {
        "symbol": symbol,
        "venue": "QFEX",
        "price_source": {"underlier": "QFEX underlier historic (reference)", "instrument": "QFEX traded instrument candles"},
        "selection": receipt,
        "requests": requests_log,
        "request_budget": {"max": MAX_MARKET_DATA_REQUESTS, "used": used},
        "source_hashes": {
            name: sha256_hex((out_dir / name).read_bytes())
            for name in ("raw_refdata.json", "raw_underlier.json", "raw_candles.json",
                         "normalized_underlier.csv", "normalized_instrument_full.csv", "loader_instrument_15m.csv")
        },
        "loader": loader_result,
        "reproduction_command": reproduction,
        "docs": [
            "https://docs.qfex.com/api-reference/rest/market-data/underlier-historic",
            "https://docs.qfex.com/api-reference/rest/market-data/candles",
            "https://docs.qfex.com/api-reference/enums.md",
        ],
        "run_utc": run_utc.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    (out_dir / "requests.json").write_text(json.dumps(requests_log, indent=2), encoding="utf-8")
    (out_dir / "coverage.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    (out_dir / "loader_check.json").write_text(json.dumps(loader_result, indent=2), encoding="utf-8")
    (out_dir / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    report = build_report(metadata, coverage, underlier_rows, full_rows)
    (out_dir / "report.md").write_text(report, encoding="utf-8")
    logger.info("qfex_probe_done", out=str(out_dir), symbol=symbol,
                underlier_rows=len(underlier_rows), instrument_rows=len(full_rows))
    return metadata


def run_offline(out_dir: Path, raw_dir: Path, start: datetime, end: datetime, symbol: str) -> dict[str, Any]:
    """Rerun finalize from preserved raw responses: ZERO market-data requests.

    Request entries are reconstructed deterministically (same endpoints and
    params as the live run); byte counts and hashes come from the preserved
    files, marked as reconstructed so they are never mistaken for fresh calls.
    """
    from_iso, to_iso = to_iso_z(start), to_iso_z(end)
    raw_refdata = (raw_dir / "raw_refdata.json").read_bytes()
    raw_underlier = (raw_dir / "raw_underlier.json").read_bytes()
    raw_candles = (raw_dir / "raw_candles.json").read_bytes()
    # Re-derive the rule-based selection from the preserved refdata so the
    # receipt stays truthful; the --symbol override only pins the fetch identity.
    rule_record, _ = select_instrument(json.loads(raw_refdata.decode("utf-8")))
    override = None if str(rule_record.get("symbol")) == symbol else symbol
    quoted = urllib.parse.quote(symbol, safe="")
    requests_log = [
        {"method": "GET", "url": f"{BASE_URL}/refdata", "endpoint": "/refdata", "params": {},
         "status": 200, "bytes": len(raw_refdata), "sha256": sha256_hex(raw_refdata),
         "elapsed_ms": None, "note": "reconstructed from preserved raw response; no live call"},
        {"method": "GET",
         "url": f"{BASE_URL}/underlier/{quoted}?{urllib.parse.urlencode({'interval': UNDERLIER_INTERVAL, 'fromISO': from_iso, 'toISO': to_iso})}",
         "endpoint": f"/underlier/{symbol}",
         "params": {"interval": UNDERLIER_INTERVAL, "fromISO": from_iso, "toISO": to_iso},
         "status": 200, "bytes": len(raw_underlier), "sha256": sha256_hex(raw_underlier),
         "elapsed_ms": None, "note": "reconstructed from preserved raw response; no live call"},
        {"method": "GET",
         "url": f"{BASE_URL}/candles/{quoted}?{urllib.parse.urlencode({'resolution': CANDLES_RESOLUTION, 'fromISO': from_iso, 'toISO': to_iso})}",
         "endpoint": f"/candles/{symbol}",
         "params": {"resolution": CANDLES_RESOLUTION, "fromISO": from_iso, "toISO": to_iso},
         "status": 200, "bytes": len(raw_candles), "sha256": sha256_hex(raw_candles),
         "elapsed_ms": None, "note": "reconstructed from preserved raw response; no live call"},
    ]
    return _finalize(out_dir, raw_refdata, raw_underlier, raw_candles, requests_log,
                     start, end, from_iso, to_iso, override, datetime.now(UTC), budget_used=3)

def run(out_dir: Path, now_utc: datetime | None = None) -> dict[str, Any]:
    now_utc = now_utc or datetime.now(UTC)
    start, end = seven_completed_utc_days(now_utc)
    from_iso, to_iso = to_iso_z(start), to_iso_z(end)
    out_dir.mkdir(parents=True, exist_ok=True)
    requests_log: list[dict[str, Any]] = []

    def fetch(endpoint: str, params: dict[str, str]) -> bytes:
        if len(requests_log) >= MAX_MARKET_DATA_REQUESTS:
            raise RuntimeError("Market-data request budget exhausted (8); stopping with partial evidence preserved.")
        status, body, elapsed_ms, final_url = http_get_json(BASE_URL + endpoint, params)
        requests_log.append(
            {
                "method": "GET",
                "url": final_url,
                "endpoint": endpoint,
                "params": params,
                "status": status,
                "bytes": len(body),
                "sha256": sha256_hex(body),
                "elapsed_ms": round(elapsed_ms, 1),
            }
        )
        logger.info("qfex_request", endpoint=endpoint, status=status, bytes=len(body))
        if status != 200:
            raise RuntimeError(f"GET {endpoint} returned HTTP {status}: {body[:500]!r}")
        return body

    # 1/3 — Refdata, then record the instrument choice BEFORE price fetches.
    raw_refdata = fetch("/refdata", {})
    record, receipt = select_instrument(json.loads(raw_refdata.decode("utf-8")))
    symbol = str(record["symbol"])
    logger.info("qfex_instrument_selected", **{k: receipt[k] for k in ("symbol", "response_index", "response_total")})

    # 2/3 — Underlier OHLC.
    raw_underlier = fetch(f"/underlier/{urllib.parse.quote(symbol, safe='')}", {"interval": UNDERLIER_INTERVAL, "fromISO": from_iso, "toISO": to_iso})

    # 3/3 — Instrument candles.
    raw_candles = fetch(f"/candles/{urllib.parse.quote(symbol, safe='')}", {"resolution": CANDLES_RESOLUTION, "fromISO": from_iso, "toISO": to_iso})

    return _finalize(out_dir, raw_refdata, raw_underlier, raw_candles, requests_log,
                     start, end, from_iso, to_iso, None, now_utc)


def build_report(
    metadata: dict[str, Any], coverage: dict[str, Any],
    underlier_rows: list[dict[str, Any]], full_rows: list[dict[str, Any]],
) -> str:
    sel = metadata["selection"]
    lines = [
        "# QFEX equity data probe — report",
        "",
        f"Symbol: `{sel['symbol']}` ({sel['base_asset']}/{sel['quote_asset']}) · Venue: QFEX · "
        f"Timeframe: 15-minute · Window (UTC): `{sel['window']['fromISO']}` → `{sel['window']['toISO']}`",
        f"Run (UTC): `{metadata['run_utc']}`",
        "",
        "## 1. Instrument selection (recorded before any price fetch)",
        "",
        f"- Rule: {sel['rule']}.",
        f"- Choice: `{sel['symbol']}` at refdata response index {sel['response_index']} of {sel['response_total']}.",
        f"- Category/status census: {json.dumps(sel['category_status_counts'])}.",
        f"- No chart was viewed before selection; the first ACTIVE EQUITY entry is {sel['symbol']} (single-stock).",
        "",
        "## 2. Requests (exact identifiers and boundaries)",
        "",
    ]
    for entry in metadata["requests"]:
        note = " (offline reconstruction: 0 new requests)" if entry.get("note") else ""
        lines.append(f"- `GET {entry['url']}` → HTTP {entry['status']}, {entry['bytes']} bytes, sha256 `{entry['sha256'][:16]}…`{note}.")
    if any(entry.get("note") for entry in metadata["requests"]):
        lines.append("- This directory was produced by offline finalize from preserved raw responses: "
                     "no new market-data requests were made for these artifacts.")
    lines += [
        f"- Budget: {metadata['request_budget']['used']}/{metadata['request_budget']['max']} market-data requests "
        "(live fetch, 20 s timeout each, sequential, no retries; offline finalize adds 0).",
        "- No auth, no private endpoints.",
        "- Base URL `https://api.qfex.com` and parameter names verified against the official docs listed in metadata.",
        f"- Wire values: underlier `interval={UNDERLIER_INTERVAL}`; candles `resolution={CANDLES_RESOLUTION}` "
        "(CandlesInterval wire value per docs enums.md; `15m` is rejected for candles with 400).",
        "",
        "## 3. Loader verification (existing reader, no strategy/bot)",
        "",
        f"- Reader: `{metadata['loader']['loader']}` with timeframe label `{metadata['loader']['timeframe_label']}`.",
        f"- Result: {metadata['loader']['rows']} rows, "
        f"{metadata['loader']['first_utc']} → {metadata['loader']['last_utc']}.",
        f"- {metadata['loader']['timestamp_convention']}",
        "- File: `loader_instrument_15m.csv` (columns: timestamp,open,high,low,close,volume).",
        "",
        "## 4. Coverage summary",
        "",
        f"- Underlier: {coverage['underlier']['rows']} rows over {coverage['underlier']['expected_intervals']} expected 15-min intervals; "
        f"missing {coverage['underlier']['missing_intervals']}, out-of-window {coverage['underlier']['extra_intervals']}, "
        f"duplicates {coverage['underlier']['duplicates']}, "
        f"nulls {coverage['underlier']['nulls_ohlc_volume']}, OHLC violations {len(coverage['underlier']['ohlc_violations'])}; "
        f"range {coverage['underlier']['first_timestamp']} → {coverage['underlier']['last_timestamp']}.",
        f"- Instrument: {coverage['instrument']['rows']} rows; missing {coverage['instrument']['missing_intervals']}, "
        f"out-of-window {coverage['instrument']['extra_intervals']}, "
        f"duplicates {coverage['instrument']['duplicates']}, nulls {coverage['instrument']['nulls_ohlc_volume']}, "
        f"OHLC violations {len(coverage['instrument']['ohlc_violations'])}; "
        f"range {coverage['instrument']['first_timestamp']} → {coverage['instrument']['last_timestamp']}.",
        f"- {coverage['underlier']['session_note']}",
        f"- {coverage['volume_note']}",
        f"- Venue field sentinels (retained verbatim, not measurements, unusable as signal): "
        f"trades null on {coverage['field_quality']['trades_null']}/{coverage['field_quality']['rows']} candles; "
        f"zero `usdVolume` on {coverage['field_quality']['zero_volume_usd']}; "
        f"zero `baseTokenVolume` on {coverage['field_quality']['zero_volume_base']}; "
        f"zero midpoint open/close on {coverage['field_quality']['zero_mid_open']}/{coverage['field_quality']['zero_mid_close']}; "
        f"zero startingOpenInterest on {coverage['field_quality']['zero_startingOpenInterest']}.",
        "",
        "## 5. Chart",
        "",
        "- `chart_underlier_vs_instrument_close.png`: underlier vs instrument closes on the full 15-minute grid; "
        "missing intervals render as visible breaks (NaN gaps, never interpolated or connected).",
        f"- Observed absolute close difference on {coverage['close_divergence']['common_intervals']} common intervals "
        f"(reference vs traded, descriptive only, not a quality verdict): "
        f"max {coverage['close_divergence']['max_abs_diff']} USD at {coverage['close_divergence']['max_at']}, "
        f"mean {coverage['close_divergence']['mean_abs_diff']} USD.",
        "",
        "## 6. Files, hashes, reproduction",
        "",
    ]
    for name, digest in metadata["source_hashes"].items():
        lines.append(f"- `{name}` sha256 `{digest}`")
    lines += [
        f"- Reproduction: `{metadata['reproduction_command']}`",
        "- Raw responses are preserved verbatim (`raw_*.json`); normalization never edits them in place.",
        "",
        "## 7. Limitations",
        "",
        "- One symbol / one timeframe / one 7-day window only; not a claim about full API history.",
        "- Session gaps are expected for equities and are reported as observed, not as corruption.",
        "- Loader `volume` is venue `usdVolume` (quote-notional); base-unit volume is retained separately.",
        "- No strategy, signal, profitability, or trading-readiness claim is made.",
    ]
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="QFEX equity data probe (research-only).")
    parser.add_argument("--out", type=str, default=None, help="Result directory")
    parser.add_argument("--from-iso", type=str, default=None, help="Override window start (ISO UTC)")
    parser.add_argument("--to-iso", type=str, default=None, help="Override window end (ISO UTC)")
    parser.add_argument("--symbol", type=str, default=None, help="Override selected symbol")
    parser.add_argument("--raw-dir", type=str, default=None,
                        help="Offline rerun from preserved raw_*.json (zero live requests)")
    args = parser.parse_args()

    now_utc = datetime.now(UTC)
    default_id = now_utc.strftime("%Y%m%dT%H%M%SZ") + "_nvda-usd_15m_7d"
    out_dir = Path(args.out) if args.out else Path("research/results/qfex_data_probe") / default_id

    if args.raw_dir:
        # Offline rerun from preserved raw responses: zero live requests.
        if not (args.from_iso and args.to_iso and args.symbol):
            raise SystemExit("--raw-dir requires --from-iso, --to-iso and --symbol (exact original boundaries)")
        start = _parse_utc_instant(args.from_iso)
        end = _parse_utc_instant(args.to_iso)
        run_offline(out_dir, Path(args.raw_dir), start, end, args.symbol)
    elif args.from_iso or args.to_iso or args.symbol:
        # Pinned rerun path with explicit boundaries.
        start = _parse_utc_instant(args.from_iso) if args.from_iso else seven_completed_utc_days(now_utc)[0]
        end = _parse_utc_instant(args.to_iso) if args.to_iso else seven_completed_utc_days(now_utc)[1]
        run_with_window(out_dir, start, end, args.symbol)
    else:
        run(out_dir, now_utc)


def run_with_window(out_dir: Path, start: datetime, end: datetime, symbol_override: str | None) -> dict[str, Any]:
    """Pinned-window rerun (same 3-request flow with explicit boundaries)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    from_iso, to_iso = to_iso_z(start), to_iso_z(end)
    requests_log: list[dict[str, Any]] = []

    def fetch(endpoint: str, params: dict[str, str]) -> bytes:
        if len(requests_log) >= MAX_MARKET_DATA_REQUESTS:
            raise RuntimeError("Market-data request budget exhausted (8); stopping with partial evidence preserved.")
        status, body, elapsed_ms, final_url = http_get_json(BASE_URL + endpoint, params)
        requests_log.append({"method": "GET", "url": final_url, "endpoint": endpoint,
                             "params": params, "status": status, "bytes": len(body),
                             "sha256": sha256_hex(body), "elapsed_ms": round(elapsed_ms, 1)})
        if status != 200:
            raise RuntimeError(f"GET {endpoint} returned HTTP {status}")
        return body

    raw_refdata = fetch("/refdata", {})
    # Resolve the symbol (selection needs refdata first), then fetch prices.
    record, _receipt = select_instrument(json.loads(raw_refdata.decode("utf-8")))
    symbol = symbol_override or str(record["symbol"])
    raw_underlier = fetch(f"/underlier/{urllib.parse.quote(symbol, safe='')}",
                          {"interval": UNDERLIER_INTERVAL, "fromISO": from_iso, "toISO": to_iso})
    raw_candles = fetch(f"/candles/{urllib.parse.quote(symbol, safe='')}",
                        {"resolution": CANDLES_RESOLUTION, "fromISO": from_iso, "toISO": to_iso})
    return _finalize(out_dir, raw_refdata, raw_underlier, raw_candles, requests_log,
                     start, end, from_iso, to_iso, symbol_override, datetime.now(UTC))


if __name__ == "__main__":
    main()

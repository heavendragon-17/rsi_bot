"""Focused fixture tests for the QFEX equity data probe.

No live API calls: every test uses synthetic or saved fixtures.
Covers schema conversion, timestamps, missing fields, invalid OHLC,
coverage accounting, and the existing loader integration.
"""

from datetime import UTC, datetime, timedelta

import pytest

from app.backtest.signal_replay_data import load_ohlcv_csv
from research.qfex_data_probe import (
    _parse_utc_instant,
    close_divergence_stats,
    coverage_summary,
    format_canonical_utc,
    instrument_field_quality,
    normalize_candles,
    normalize_underlier,
    ohlc_violations,
    run_offline,
    select_instrument,
    seven_completed_utc_days,
)


def _refdata() -> dict:
    return {
        "data": [
            {"symbol": "CL-USD", "product_category": "COMMODITY", "status": "ACTIVE",
             "base_asset": "CL", "quote_asset": "USD"},
            {"symbol": "NVDA-USD", "product_category": "EQUITY", "status": "ACTIVE",
             "base_asset": "NVDA", "quote_asset": "USD"},
            {"symbol": "AAPL-USD", "product_category": "EQUITY", "status": "ACTIVE",
             "base_asset": "AAPL", "quote_asset": "USD"},
            {"symbol": "OLD-USD", "product_category": "EQUITY", "status": "DELISTED",
             "base_asset": "OLD", "quote_asset": "USD"},
        ]
    }


def _candle(started_at: str, **overrides) -> dict:
    candle = {
        "startedAt": started_at,
        "ticker": "NVDA-USD",
        "resolution": "15MINS",
        "open": "218.66",
        "high": "218.70",
        "low": "218.60",
        "close": "218.64",
        "baseTokenVolume": "1.5",
        "usdVolume": "327.99",
        "startingOpenInterest": "0",
        "orderbookMidPriceOpen": "218.63",
        "orderbookMidPriceClose": "218.65",
        "trades": 12,
    }
    candle.update(overrides)
    return candle


# --- selection -----------------------------------------------------------

def test_select_instrument_picks_first_active_equity_without_prices():
    record, receipt = select_instrument(_refdata())
    assert record["symbol"] == "NVDA-USD"
    assert receipt["response_index"] == 1
    assert receipt["response_total"] == 4
    assert "no price data consulted" in receipt["rule"]


def test_select_instrument_raises_when_no_active_equity():
    with pytest.raises(ValueError, match="No ACTIVE EQUITY"):
        select_instrument({"data": [{"symbol": "CL-USD", "product_category": "COMMODITY", "status": "ACTIVE"}]})


def test_seven_completed_utc_days_window():
    now = datetime(2026, 9, 20, 10, 30, tzinfo=UTC)
    start, end = seven_completed_utc_days(now)
    assert (start, end) == (datetime(2026, 9, 13, tzinfo=UTC), datetime(2026, 9, 20, tzinfo=UTC))
    assert (end - start) == timedelta(days=7)


# --- timestamps ----------------------------------------------------------

def test_parse_utc_instant_accepts_z_and_offset():
    assert _parse_utc_instant("2026-09-13T00:15:00Z") == datetime(2026, 9, 13, 0, 15, tzinfo=UTC)
    assert _parse_utc_instant("2026-09-13T00:15:00z") == datetime(2026, 9, 13, 0, 15, tzinfo=UTC)
    assert _parse_utc_instant("2026-09-13T02:15:00+02:00") == datetime(2026, 9, 13, 0, 15, tzinfo=UTC)


def test_parse_utc_instant_only_strips_trailing_z():
    with pytest.raises(ValueError):
        _parse_utc_instant("2026-09-13T00:15:00Zulu")  # interior/trailing junk is not a timezone


def test_parse_utc_instant_rejects_naive():
    with pytest.raises(ValueError, match="Naive timestamp"):
        _parse_utc_instant("2026-09-13 00:15:00")


def test_canonical_format_is_tz_aware_utc():
    out = format_canonical_utc(datetime(2026, 9, 13, 0, 15, tzinfo=UTC))
    assert out == "2026-09-13 00:15:00+00:00"
    assert _parse_utc_instant(out.replace(" ", "T").replace("+00:00", "Z")) == datetime(2026, 9, 13, 0, 15, tzinfo=UTC)


def test_canonical_format_preserves_fractional_seconds():
    out = format_canonical_utc(datetime(2026, 9, 13, 0, 15, 0, 123456, tzinfo=UTC))
    assert out == "2026-09-13 00:15:00.123456+00:00"
    assert _parse_utc_instant(out.replace(" ", "T")) == datetime(2026, 9, 13, 0, 15, 0, 123456, tzinfo=UTC)


# --- schema conversion ---------------------------------------------------

def test_normalize_underlier_schema_and_sort():
    rows = normalize_underlier([
        {"symbol": "NVDA-USD", "interval": "15m", "windowStart": "2026-09-13T00:30:00Z",
         "openPrice": 218.6, "highPrice": 218.7, "lowPrice": 218.5, "closePrice": 218.6},
        {"symbol": "NVDA-USD", "interval": "15m", "windowStart": "2026-09-13T00:00:00Z",
         "openPrice": 218.6, "highPrice": 218.6, "lowPrice": 218.6, "closePrice": 218.6},
    ])
    assert [r["timestamp"] for r in rows] == ["2026-09-13 00:00:00+00:00", "2026-09-13 00:30:00+00:00"]
    assert "volume" not in rows[0]  # underlier carries no volume: never invented
    assert rows[0]["windowStart"] == "2026-09-13T00:00:00Z"  # raw source instant preserved


def test_normalize_underlier_missing_field_raises():
    with pytest.raises(ValueError, match="missing required field"):
        normalize_underlier([{"symbol": "NVDA-USD", "windowStart": "2026-09-13T00:00:00Z", "openPrice": 1.0}])


def test_normalize_candles_volume_mapping_and_optional_trades():
    loader_rows, full_rows = normalize_candles([
        _candle("2026-09-13T00:30:00Z"),
        {**_candle("2026-09-13T00:00:00Z"), "trades": None},  # trades absent upstream: tolerated
    ])
    assert [r["timestamp"] for r in loader_rows] == ["2026-09-13 00:00:00+00:00", "2026-09-13 00:30:00+00:00"]
    assert loader_rows[0]["volume"] == pytest.approx(327.99)  # volume := venue usdVolume
    assert set(loader_rows[0]) == {"timestamp", "open", "high", "low", "close", "volume"}
    assert full_rows[0]["volume_base"] == "1.5"  # base volume retained verbatim
    assert full_rows[0]["mid_open"] == "218.63" and full_rows[0]["mid_close"] == "218.65"
    assert full_rows[0]["trades"] is None  # 00:00 row carries the null trades
    assert full_rows[1]["trades"] == 12


def test_normalize_candles_missing_required_raises():
    bad = _candle("2026-09-13T00:00:00Z")
    del bad["usdVolume"]
    with pytest.raises(ValueError, match="Candle 0 missing required field"):
        normalize_candles([bad])


def test_normalize_candles_non_numeric_reports_row_position():
    bad = _candle("2026-09-13T00:00:00Z", close="")
    with pytest.raises(ValueError, match="Candle 0 has non-numeric"):
        normalize_candles([bad])
    with pytest.raises(ValueError, match="Underlier point 0 has non-numeric"):
        normalize_underlier([
            {"symbol": "NVDA-USD", "interval": "15m", "windowStart": "2026-09-13T00:00:00Z",
             "openPrice": 1.0, "highPrice": 1.0, "lowPrice": 1.0, "closePrice": "bad"},
        ])


def test_degenerate_venue_shape_passes_through_verbatim():
    """Real degenerate shape: null trades, "0" mids/OI/base-volume are kept, flagged downstream."""
    loader_rows, full_rows = normalize_candles([
        {**_candle("2026-09-13T00:00:00Z"), "trades": None, "baseTokenVolume": "0",
         "orderbookMidPriceOpen": "0", "orderbookMidPriceClose": "0",
         "startingOpenInterest": "0", "usdVolume": "0"},
    ])
    assert full_rows[0]["trades"] is None
    assert full_rows[0]["volume_base"] == "0"
    assert loader_rows[0]["volume"] == 0.0  # passed through, never invented
    quality = instrument_field_quality(full_rows)
    assert quality["trades_null"] == 1
    assert quality["zero_volume_usd"] == 1
    assert quality["zero_mid_open"] == 1 and quality["zero_mid_close"] == 1
    assert quality["zero_startingOpenInterest"] == 1


# --- invalid OHLC ----------------------------------------------------------

def test_ohlc_violations_flag_inversions_and_non_finite():
    rows = [
        {"timestamp": "t0", "open": 1.0, "high": 0.5, "low": 0.4, "close": 0.9},  # high < open/close
        {"timestamp": "t1", "open": 1.0, "high": 1.1, "low": 1.5, "close": 1.0},  # low > body
        {"timestamp": "t2", "open": 1.0, "high": float("nan"), "low": 0.9, "close": 1.0},
        {"timestamp": "t3", "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0},  # clean
    ]
    findings = ohlc_violations(rows)
    assert [f["timestamp"] for f in findings] == ["t0", "t1", "t2"]


# --- coverage --------------------------------------------------------------

def test_coverage_counts_missing_duplicates_and_range():
    start = datetime(2026, 9, 13, tzinfo=UTC)
    end = datetime(2026, 9, 13, 1, 0, tzinfo=UTC)  # 4 expected intervals
    rows = [
        {"timestamp": "2026-09-13 00:00:00+00:00", "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0},
        {"timestamp": "2026-09-13 00:00:00+00:00", "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0},
        {"timestamp": "2026-09-13 00:30:00+00:00", "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0},
    ]
    summary = coverage_summary(rows, start, end)
    assert summary["expected_intervals"] == 4
    assert summary["missing_intervals"] == 2  # 00:15, 00:45 absent
    assert summary["extra_intervals"] == 0
    assert summary["duplicates"] == 1
    assert summary["first_timestamp"] == "2026-09-13T00:00:00Z"
    assert summary["last_timestamp"] == "2026-09-13T00:30:00Z"
    assert "not classified as corruption" in summary["session_note"]


def test_coverage_flags_out_of_window_and_volume_nulls():
    start = datetime(2026, 9, 13, tzinfo=UTC)
    end = datetime(2026, 9, 13, 1, 0, tzinfo=UTC)
    rows = [
        {"timestamp": "2026-09-13 00:00:00+00:00", "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 5.0},
        {"timestamp": "2026-09-13 05:00:00+00:00", "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": None},
    ]
    summary = coverage_summary(rows, start, end)
    assert summary["extra_intervals"] == 1  # 05:00 is outside the window
    assert summary["extra_list"] == ["2026-09-13T05:00:00Z"]
    assert summary["nulls_ohlc_volume"] == 1  # the null volume is counted


# --- close divergence --------------------------------------------------------

def test_close_divergence_stats_common_intervals_only():
    underlier = [
        {"timestamp": "2026-09-13 00:00:00+00:00", "close": 100.0},
        {"timestamp": "2026-09-13 00:15:00+00:00", "close": 102.0},
        {"timestamp": "2026-09-13 00:30:00+00:00", "close": 101.0},  # no instrument leg: ignored
    ]
    full = [
        {"timestamp": "2026-09-13 00:00:00+00:00", "close": 100.5},
        {"timestamp": "2026-09-13 00:15:00+00:00", "close": 101.0},
    ]
    stats = close_divergence_stats(underlier, full)
    assert stats["common_intervals"] == 2
    assert stats["max_abs_diff"] == pytest.approx(1.0)
    assert stats["max_at"] == "2026-09-13T00:15:00Z"
    assert stats["mean_abs_diff"] == pytest.approx(0.75)


def test_close_divergence_stats_empty():
    assert close_divergence_stats([], [])["common_intervals"] == 0


# --- existing loader integration (synthetic fixture, no live calls) --------

def test_loader_integration_synthetic_fixture(tmp_path):
    loader_rows, _ = normalize_candles([
        _candle("2026-09-13T00:00:00Z"),
        _candle("2026-09-13T00:15:00Z"),
        _candle("2026-09-13T00:30:00Z"),
    ])
    csv_path = tmp_path / "loader_instrument_15m.csv"
    import csv as _csv

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = _csv.DictWriter(handle, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(loader_rows)
    frame = load_ohlcv_csv(csv_path, "15m")
    assert len(frame) == 3
    assert frame.index.min().strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-09-13T00:00:00Z"
    assert frame.index.max().strftime("%Y-%m-%dT%H:%M:%SZ") == "2026-09-13T00:30:00Z"
    assert (frame["volume"] == 327.99).all()


def test_loader_rejects_duplicate_candle_opens(tmp_path):
    loader_rows, _ = normalize_candles([_candle("2026-09-13T00:00:00Z")])
    csv_path = tmp_path / "dup.csv"
    import csv as _csv

    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = _csv.DictWriter(handle, fieldnames=["timestamp", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        writer.writerows(loader_rows + loader_rows)
    from app.backtest.signal_replay_models import SignalReplayInputError

    with pytest.raises(SignalReplayInputError, match="duplicate"):
        load_ohlcv_csv(csv_path, "15m")


# --- end-to-end offline finalize (synthetic raws, zero live calls) -----------

def test_run_offline_produces_full_artifact_set(tmp_path):
    import json as _json

    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "raw_refdata.json").write_text(_json.dumps({"data": [
        {"symbol": "CL-USD", "product_category": "COMMODITY", "status": "ACTIVE",
         "base_asset": "CL", "quote_asset": "USD"},
        {"symbol": "NVDA-USD", "product_category": "EQUITY", "status": "ACTIVE",
         "base_asset": "NVDA", "quote_asset": "USD"},
    ]}), encoding="utf-8")
    underlier = {"data": [
        {"symbol": "NVDA-USD", "interval": "15m", "windowStart": f"2026-09-13T00:{m:02d}:00Z",
         "openPrice": 100.0, "highPrice": 100.5, "lowPrice": 99.5, "closePrice": 100.0 + m / 100}
        for m in (0, 15, 30, 45)
    ]}
    (raw_dir / "raw_underlier.json").write_text(_json.dumps(underlier), encoding="utf-8")
    candles = {"candles": [
        {**_candle(f"2026-09-13T00:{m:02d}:00Z"), "startedAt": f"2026-09-13T00:{m:02d}:00Z"}
        for m in (0, 15, 30, 45)
    ]}
    (raw_dir / "raw_candles.json").write_text(_json.dumps(candles), encoding="utf-8")

    out_dir = tmp_path / "out"
    metadata = run_offline(out_dir, raw_dir, datetime(2026, 9, 13, tzinfo=UTC),
                           datetime(2026, 9, 13, 1, 0, tzinfo=UTC), "NVDA-USD")

    for name in ("raw_refdata.json", "raw_underlier.json", "raw_candles.json",
                 "normalized_underlier.csv", "normalized_instrument_full.csv",
                 "loader_instrument_15m.csv", "requests.json", "coverage.json",
                 "loader_check.json", "metadata.json", "report.md",
                 "chart_underlier_vs_instrument_close.png"):
        assert (out_dir / name).exists(), name
    assert metadata["symbol"] == "NVDA-USD"
    assert metadata["loader"]["rows"] == 4
    assert all(entry.get("note") for entry in metadata["requests"])  # reconstructions marked
    assert metadata["request_budget"] == {"max": 8, "used": 3}
    with (out_dir / "loader_instrument_15m.csv").open(encoding="utf-8") as handle:
        assert handle.readline().strip() == "timestamp,open,high,low,close,volume"
    coverage = _json.loads((out_dir / "coverage.json").read_text(encoding="utf-8"))
    assert coverage["instrument"]["rows"] == 4
    assert coverage["instrument"]["missing_intervals"] == 0
    assert coverage["instrument"]["extra_intervals"] == 0

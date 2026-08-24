"""Point-in-time data/replay tests for the dedicated Core V2.1 path."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from app.backtest.core_v2_1.audit import to_jsonable
from app.backtest.core_v2_1.binance_data import (
    BinanceDataError,
    approved_binance_symbols,
    refresh_recent_closed_candles,
    resolve_server_now,
)
from app.backtest.core_v2_1.coverage import (
    CORE_V2_1_UNIVERSE,
    EXPECTED_LOCAL_SIX,
    assert_pre_download_local_six,
    data_identity_for_symbol,
    scan_local_coverage,
)
from app.backtest.core_v2_1.data import (
    CandleDataError,
    build_point_in_time_context,
    load_stored_candles,
    normalize_stored_candles,
    resample_closed_candles,
)
from app.backtest.core_v2_1.replay import (
    CoreV21PointInTimeReplay,
    ReplayFrames,
    load_available_universe,
    replay_metadata,
)
from app.trading.strategy.core_v2_1 import (
    FEATURE_ANCHOR_M15_OPEN,
    FEATURE_ANCHOR_VERSION,
    INSTRUMENTS,
    TRADE_CANDIDATES,
    ReasonCode,
)


def _stored_rows(
    start: str = "2026-01-01 07:00:00",
    periods: int = 8,
    *,
    freq: str = "15min",
    base: float = 100.0,
) -> pd.DataFrame:
    timestamps = pd.date_range(start, periods=periods, freq=freq)
    opens = [base + index for index in range(periods)]
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "open": opens,
            "high": [value + 2 for value in opens],
            "low": [value - 2 for value in opens],
            "close": [value + 1 for value in opens],
            "volume": [10 + index for index in range(periods)],
        }
    )


def _feature(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["ema21"] = result["close"] - 1
    result["ema200"] = result["close"] - 2
    result["atr14"] = 2.0
    result["rsi21"] = 60.0
    result["rsi_ema9"] = 55.0
    result["rsi_wma45"] = 50.0
    return result


def test_storage_timestamp_is_utc7_open_and_index_is_utc_close() -> None:
    raw = _stored_rows(periods=2)
    loaded = normalize_stored_candles(raw, now="2026-01-01T00:20:00Z")

    assert loaded.frame.index.tolist() == [pd.Timestamp("2026-01-01T00:15:00Z")]
    assert loaded.frame.iloc[0]["open_at"] == pd.Timestamp("2026-01-01T00:00:00Z")
    assert loaded.report.dropped_forming_rows == 1
    assert loaded.report.last_closed_at == pd.Timestamp("2026-01-01T00:15:00Z")


def test_synthetic_btc_fixture_is_rejected_by_filename(tmp_path: Path) -> None:
    path = tmp_path / "BTC_USDT_15m.csv"
    _stored_rows(periods=1).to_csv(path, index=False)

    with pytest.raises(CandleDataError, match="synthetic test fixture"):
        load_stored_candles(path, now="2026-01-02T00:00:00Z")


@pytest.mark.parametrize("mutation, message", [("duplicate", "duplicate"), ("gap", "gap")])
def test_strict_loader_rejects_duplicate_and_gap_cadence(mutation: str, message: str) -> None:
    raw = _stored_rows(periods=5)
    if mutation == "duplicate":
        raw.loc[3, "timestamp"] = raw.loc[2, "timestamp"]
    else:
        raw = raw.drop(index=2).reset_index(drop=True)

    with pytest.raises(CandleDataError, match=message):
        normalize_stored_candles(raw, now="2026-01-02T00:00:00Z", strict=True)


def test_resampling_is_utc_anchored_and_drops_partial_buckets() -> None:
    full = normalize_stored_candles(
        _stored_rows(periods=16), now="2026-01-02T00:00:00Z"
    ).frame
    h1 = resample_closed_candles(full, "1h")
    h4 = resample_closed_candles(full, "4h")

    assert h1.index.tolist() == list(pd.date_range("2026-01-01T01:00:00Z", periods=4, freq="1h"))
    assert h4.index.tolist() == [pd.Timestamp("2026-01-01T04:00:00Z")]
    assert h4.iloc[0]["open"] == 100.0
    assert h4.iloc[0]["high"] == 117.0
    assert h4.iloc[0]["low"] == 98.0
    assert h4.iloc[0]["close"] == 116.0
    assert h4.iloc[0]["volume"] == sum(range(10, 26))

    partial_source = normalize_stored_candles(
        _stored_rows(start="2026-01-01 07:15:00", periods=15),
        now="2026-01-02T00:00:00Z",
    ).frame
    partial_h1 = resample_closed_candles(partial_source, "1h")
    assert partial_h1.index.tolist() == list(
        pd.date_range("2026-01-01T02:00:00Z", periods=3, freq="1h")
    )
    assert resample_closed_candles(partial_source, "4h").empty


def test_resampling_rejects_off_grid_interior_source_row() -> None:
    source = normalize_stored_candles(
        _stored_rows(periods=8), now="2026-01-02T00:00:00Z"
    ).frame
    changed = source.index.to_list()
    changed[3] = changed[3] + pd.Timedelta(minutes=1)
    source.index = pd.DatetimeIndex(changed, name="closed_at")

    with pytest.raises(CandleDataError, match="UTC 15-minute grid"):
        resample_closed_candles(source, "1h")


def test_point_in_time_context_uses_exact_expected_closed_boundaries() -> None:
    m15 = normalize_stored_candles(
        _stored_rows(periods=32), now="2026-01-02T00:00:00Z"
    ).frame
    h1 = resample_closed_candles(m15, "1h")
    h4 = resample_closed_candles(m15, "4h")
    as_of = pd.Timestamp("2026-01-01T04:15:00Z")

    context = build_point_in_time_context(
        symbol="ETHUSDT", as_of=as_of, m15=m15, alt_h1=h1, btc_h1=h1, btc_h4=h4
    )

    assert context is not None
    assert context.current_m15.closed_at == as_of
    assert context.alt_h1.closed_at == pd.Timestamp("2026-01-01T04:00:00Z")
    assert context.btc_h1.closed_at == pd.Timestamp("2026-01-01T04:00:00Z")
    assert context.btc_h4.closed_at == pd.Timestamp("2026-01-01T04:00:00Z")
    assert all(pd.Timestamp(value) <= as_of for value in context.context_closed_at.values())

    stale_h1 = h1.drop(pd.Timestamp("2026-01-01T04:00:00Z"))
    assert (
        build_point_in_time_context(
            symbol="ETHUSDT",
            as_of=as_of,
            m15=m15,
            alt_h1=stale_h1,
            btc_h1=h1,
            btc_h4=h4,
        )
        is None
    )


def test_coverage_identifies_exact_pre_download_six_and_venue_identity(tmp_path: Path) -> None:
    for symbol in (*EXPECTED_LOCAL_SIX, "BTCUSDT"):
        (tmp_path / f"{symbol}_15m.csv").touch()
    (tmp_path / "BTC_USDT_15m.csv").touch()
    report = scan_local_coverage(tmp_path, validate=False)

    assert report.available_count == 6
    assert report.available_symbols == EXPECTED_LOCAL_SIX
    assert len(report.missing_symbols) == 19
    assert report.benchmark_available
    assert report.synthetic_btc_fixture_present
    assert_pre_download_local_six(report)

    pump = data_identity_for_symbol("PUMP")
    assert pump.venue == "HYPERLIQUID_PERP"
    assert pump.venue_instrument == "PUMP/USDC:USDC"
    assert pump.filename == "HYPERLIQUID__PUMP_USDC_PERP_15m.csv"
    assert "PUMPUSDT" not in pump.filename


def test_validated_coverage_rejects_short_candidate_and_corrupt_btc(tmp_path: Path) -> None:
    _stored_rows(periods=8).to_csv(tmp_path / "ETHUSDT_15m.csv", index=False)
    corrupt_btc = _stored_rows(periods=8)
    corrupt_btc.loc[3, "timestamp"] = corrupt_btc.loc[2, "timestamp"]
    corrupt_btc.to_csv(tmp_path / "BTCUSDT_15m.csv", index=False)

    report = scan_local_coverage(
        tmp_path,
        validate=True,
        now="2026-01-02T00:00:00Z",
    )

    assert "ETHUSDT" in report.invalid_symbols
    assert report.benchmark_available
    assert report.benchmark_valid is False
    assert report.benchmark_error is not None
    assert "duplicate" in report.benchmark_error
    assert not report.is_complete


@pytest.mark.parametrize("symbol", ["ETHUSDT", "BTCUSDT"])
def test_validated_coverage_rejects_rolling_window_that_lost_feature_anchor(
    tmp_path: Path,
    symbol: str,
) -> None:
    stored_anchor = (
        pd.Timestamp(FEATURE_ANCHOR_M15_OPEN) + pd.Timedelta(hours=7)
    ).tz_localize(None)
    rolling_start = stored_anchor + pd.Timedelta(minutes=15)
    _stored_rows(start=rolling_start.isoformat(), periods=5_000).to_csv(
        tmp_path / f"{symbol}_15m.csv",
        index=False,
    )

    report = scan_local_coverage(
        tmp_path,
        validate=True,
        now="2026-08-21T00:00:00Z",
    )

    if symbol == "BTCUSDT":
        assert report.benchmark_valid is False
        assert report.benchmark_error is not None
        assert "feature anchor is incomplete" in report.benchmark_error
    else:
        assert symbol in report.invalid_symbols
        item = next(file for file in report.files if file.symbol == symbol)
        assert item.error is not None
        assert "feature anchor is incomplete" in item.error
    assert not report.is_complete


def test_audit_enum_serialization_uses_stable_reason_value() -> None:
    assert to_jsonable(ReasonCode.M15_EMA21_NOT_RISING) == "M15_EMA21_NOT_RISING"


def test_approved_binance_refresh_set_is_24_alts_plus_btc() -> None:
    symbols = approved_binance_symbols()
    assert len(symbols) == 25
    assert symbols[-1] == "BTCUSDT"
    assert "PUMP" not in symbols


def test_replay_universe_and_data_identities_match_authoritative_core_config() -> None:
    assert CORE_V2_1_UNIVERSE == TRADE_CANDIDATES
    for symbol in TRADE_CANDIDATES:
        identity = data_identity_for_symbol(symbol)
        assert identity.strategy_symbol == symbol
        assert identity.venue == INSTRUMENTS[symbol].venue.value
        assert identity.venue_instrument == INSTRUMENTS[symbol].venue_symbol


def test_general_loader_uses_structural_hyperliquid_path_and_never_substitutes(
    tmp_path: Path,
) -> None:
    raw = _stored_rows(start="2026-06-29 18:15:00", periods=8)
    raw.to_csv(tmp_path / "HYPERLIQUID__PUMP_USDC_PERP_15m.csv", index=False)
    raw.to_csv(tmp_path / "BTCUSDT_15m.csv", index=False)
    # A misleading Binance-style file must not affect the identity lookup.
    raw.assign(close=999.0).to_csv(tmp_path / "PUMPUSDT_15m.csv", index=False)

    loaded = load_available_universe(
        tmp_path,
        symbols=["PUMP"],
        now="2026-07-01T00:00:00Z",
    )

    assert tuple(loaded.alt_m15) == ("PUMP",)
    assert loaded.alt_m15["PUMP"].iloc[0]["close"] == 101.0
    pump_manifest = loaded.input_manifest[0]
    assert pump_manifest.venue == "HYPERLIQUID_PERP"
    assert pump_manifest.venue_instrument == "PUMP/USDC:USDC"
    assert Path(pump_manifest.path).name == "HYPERLIQUID__PUMP_USDC_PERP_15m.csv"
    assert loaded.alt_m15["PUMP"].iloc[0]["open_at"] == pd.Timestamp(
        FEATURE_ANCHOR_M15_OPEN
    )


def test_loader_fails_closed_when_first_feature_anchor_candle_is_missing(
    tmp_path: Path,
) -> None:
    missing_anchor = _stored_rows(start="2026-06-29 18:30:00", periods=8)
    missing_anchor.to_csv(
        tmp_path / "HYPERLIQUID__PUMP_USDC_PERP_15m.csv",
        index=False,
    )
    _stored_rows(start="2026-06-29 18:15:00", periods=8).to_csv(
        tmp_path / "BTCUSDT_15m.csv",
        index=False,
    )

    with pytest.raises(CandleDataError, match="feature anchor is incomplete"):
        load_available_universe(
            tmp_path,
            symbols=["PUMP"],
            now="2026-07-01T00:00:00Z",
        )

    with pytest.raises(CandleDataError, match="Unknown.*PUMPUSDT"):
        load_available_universe(tmp_path, symbols=["PUMPUSDT"])


def test_full_universe_loader_reports_each_missing_identity_without_substitution(
    tmp_path: Path,
) -> None:
    with pytest.raises(CandleDataError, match="no substitution allowed") as raised:
        load_available_universe(tmp_path, require_all=True)

    message = str(raised.value)
    assert "PUMP [HYPERLIQUID_PERP PUMP/USDC:USDC]" in message
    assert "HYPERLIQUID__PUMP_USDC_PERP_15m.csv" in message
    assert "BTCUSDT [BINANCE_FUTURES BTC/USDT:USDT]" in message


@dataclass(frozen=True)
class _State:
    count: int = 0


def test_replay_and_ledger_are_point_in_time_ordered_and_byte_deterministic(
    tmp_path: Path,
) -> None:
    source = normalize_stored_candles(
        _stored_rows(periods=32), now="2026-01-02T00:00:00Z"
    ).frame
    m15 = _feature(source)
    h1 = _feature(resample_closed_candles(source, "1h"))
    h4 = _feature(resample_closed_candles(source, "4h"))
    seen: list[tuple[str, pd.Timestamp]] = []

    def evaluator(evaluation_input, state: _State):
        seen.append((evaluation_input.symbol, evaluation_input.current_m15.closed_at))
        return SimpleNamespace(
            decision=SimpleNamespace(kind="QUIET", reasons=(), event=None),
            next_state=_State(state.count + 1),
        )

    # Deliberately reverse insertion order; canonical universe order must still
    # break equal-timestamp ties as ETH then SOL.
    frames = ReplayFrames(
        alt_m15={"SOLUSDT": m15, "ETHUSDT": m15},
        alt_h1={"SOLUSDT": h1, "ETHUSDT": h1},
        btc_h1=h1,
        btc_h4=h4,
    )
    replay = CoreV21PointInTimeReplay(frames, evaluator=evaluator, state_factory=_State)
    result = replay.run(start="2026-01-01T05:00:00Z", end="2026-01-01T05:15:00Z")

    assert result.processed_events == 4
    assert result.evaluated_events == 4
    assert result.warmup_processed_events > 0
    assert result.ledger.records[0].state_before.count > 0
    assert [symbol for symbol, _ in seen[-4:]] == ["ETHUSDT", "SOLUSDT", "ETHUSDT", "SOLUSDT"]
    for record in result.ledger.records:
        assert all(pd.Timestamp(value) <= record.trigger_closed_at for value in record.context_closed_at.values())

    metadata = replay_metadata(result=result)
    assert metadata["strategy_version"] == "2.1"
    assert metadata["feature_anchor_version"] == FEATURE_ANCHOR_VERSION
    assert metadata["feature_anchor_m15_open"] == FEATURE_ANCHOR_M15_OPEN.isoformat()
    assert metadata["evaluated_events"] == 4
    assert metadata["skipped_events"] == 0
    first_paths = result.ledger.export(tmp_path / "first", metadata=metadata)
    second_paths = result.ledger.export(tmp_path / "second", metadata=metadata)
    assert first_paths.jsonl.read_bytes() == second_paths.jsonl.read_bytes()
    assert first_paths.csv.read_bytes() == second_paths.csv.read_bytes()
    assert first_paths.metadata.read_bytes() == second_paths.metadata.read_bytes()


def test_replay_adapter_constructs_finalized_core_evaluation_contract() -> None:
    source = normalize_stored_candles(
        _stored_rows(periods=32), now="2026-01-02T00:00:00Z"
    ).frame
    m15 = _feature(source)
    h1 = _feature(resample_closed_candles(source, "1h"))
    h4 = _feature(resample_closed_candles(source, "4h"))
    replay = CoreV21PointInTimeReplay(
        ReplayFrames(
            alt_m15={"ETHUSDT": m15},
            alt_h1={"ETHUSDT": h1},
            btc_h1=h1,
            btc_h4=h4,
        )
    )

    result = replay.run(start="2026-01-01T05:00:00Z", end="2026-01-01T05:15:00Z")

    assert result.processed_events == 2
    assert result.evaluated_events == 2
    assert result.not_ready_events == 0
    assert result.ledger.records[0].decision.kind.value == "QUIET"


def test_replay_constructor_rejects_gap_even_when_loader_is_bypassed() -> None:
    source = normalize_stored_candles(
        _stored_rows(periods=32), now="2026-01-02T00:00:00Z"
    ).frame
    m15 = _feature(source).drop(source.index[10])
    h1 = _feature(resample_closed_candles(source, "1h"))
    h4 = _feature(resample_closed_candles(source, "4h"))

    with pytest.raises(CandleDataError, match="exact.*cadence"):
        CoreV21PointInTimeReplay(
            ReplayFrames(
                alt_m15={"ETHUSDT": m15},
                alt_h1={"ETHUSDT": h1},
                btc_h1=h1,
                btc_h4=h4,
            )
        )


class _FakeBinance:
    def __init__(self, *, server_now: str, missing_open: pd.Timestamp | None = None) -> None:
        self.server_now = pd.Timestamp(server_now)
        self.missing_open = missing_open
        self.calls: list[tuple[str, int, int]] = []

    def fetch_ohlcv(self, symbol, timeframe, since=None, limit=None, params=None):
        assert since is not None
        assert limit is not None
        self.calls.append((symbol, since, limit))
        start = pd.Timestamp(since, unit="ms", tz="UTC")
        # Return the requested rows plus a forming row.  Production code must
        # independently filter against authoritative server time.
        opens = pd.date_range(start, periods=limit + 1, freq="15min")
        rows = []
        for position, opened_at in enumerate(opens):
            if self.missing_open is not None and opened_at == self.missing_open:
                continue
            value = 200.0 + position
            rows.append(
                [
                    int(opened_at.timestamp() * 1_000),
                    value,
                    value + 2,
                    value - 2,
                    value + 1,
                    10.0,
                ]
            )
        return rows


def test_binance_refresh_replaces_recent_window_preserves_history_and_excludes_forming(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ETHUSDT_15m.csv"
    anchor_local = (
        pd.Timestamp(FEATURE_ANCHOR_M15_OPEN)
        + pd.Timedelta(hours=7)
        - pd.Timedelta(minutes=15)
    ).tz_localize(None)
    _stored_rows(start=anchor_local.isoformat(), periods=2, base=50.0).to_csv(
        path,
        index=False,
    )
    exchange = _FakeBinance(server_now="2026-06-29T12:22:00Z")

    result = refresh_recent_closed_candles(
        exchange,
        symbol="ETHUSDT",
        data_dir=tmp_path,
        candle_count=4,
        server_now=exchange.server_now,
    )

    loaded = load_stored_candles(path, now=exchange.server_now)
    assert result.recent_candles == 4
    assert result.preserved_older_candles == 1
    assert result.feature_anchor_open_at == FEATURE_ANCHOR_M15_OPEN.isoformat()
    assert result.sha256
    assert len(loaded.frame) == 5
    assert loaded.frame.index[-1] == pd.Timestamp("2026-06-29T12:15:00Z")
    assert all(loaded.frame.index <= exchange.server_now)
    assert not list(tmp_path.glob(".*.tmp"))

    original = path.read_bytes()
    refresh_recent_closed_candles(
        exchange,
        symbol="ETHUSDT",
        data_dir=tmp_path,
        candle_count=4,
        server_now=exchange.server_now,
    )
    assert path.read_bytes() == original


def test_binance_incomplete_refresh_fails_without_overwriting_existing_file(tmp_path: Path) -> None:
    path = tmp_path / "ETHUSDT_15m.csv"
    anchor_local = (
        pd.Timestamp(FEATURE_ANCHOR_M15_OPEN)
        + pd.Timedelta(hours=7)
        - pd.Timedelta(minutes=15)
    ).tz_localize(None)
    _stored_rows(start=anchor_local.isoformat(), periods=2, base=50.0).to_csv(
        path,
        index=False,
    )
    original = path.read_bytes()
    missing = pd.Timestamp("2026-06-29T11:45:00Z")
    exchange = _FakeBinance(
        server_now="2026-06-29T12:22:00Z",
        missing_open=missing,
    )

    with pytest.raises(BinanceDataError, match="incomplete"):
        refresh_recent_closed_candles(
            exchange,
            symbol="ETHUSDT",
            data_dir=tmp_path,
            candle_count=4,
            server_now=exchange.server_now,
        )

    assert path.read_bytes() == original


def test_binance_refresh_rejects_conflicting_duplicate_in_preserved_anchor_prefix(
    tmp_path: Path,
) -> None:
    path = tmp_path / "ETHUSDT_15m.csv"
    anchor_local = (
        pd.Timestamp(FEATURE_ANCHOR_M15_OPEN)
        + pd.Timedelta(hours=7)
        - pd.Timedelta(minutes=15)
    ).tz_localize(None)
    existing = _stored_rows(
        start=anchor_local.isoformat(),
        periods=10,
        base=50.0,
    )
    conflicting = existing.iloc[[0]].copy()
    conflicting.loc[:, "close"] = conflicting["close"] + 0.5
    with_duplicate = pd.concat(
        [existing.iloc[[0]], conflicting, existing.iloc[1:]],
        ignore_index=True,
    )
    with_duplicate.to_csv(path, index=False)
    original = path.read_bytes()
    exchange = _FakeBinance(server_now="2026-06-29T14:22:00Z")

    with pytest.raises(BinanceDataError, match="conflicting duplicate"):
        refresh_recent_closed_candles(
            exchange,
            symbol="ETHUSDT",
            data_dir=tmp_path,
            candle_count=4,
            server_now=exchange.server_now,
        )

    assert exchange.calls == []
    assert path.read_bytes() == original


def test_binance_reconciliation_repairs_existing_interior_gap(tmp_path: Path) -> None:
    path = tmp_path / "ETHUSDT_15m.csv"
    anchor_local = (
        pd.Timestamp(FEATURE_ANCHOR_M15_OPEN)
        + pd.Timedelta(hours=7)
        - pd.Timedelta(minutes=15)
    ).tz_localize(None)
    existing = _stored_rows(
        start=anchor_local.isoformat(),
        periods=5,
        base=50.0,
    ).drop(index=2)
    existing.to_csv(path, index=False)
    exchange = _FakeBinance(server_now="2026-06-29T13:07:00Z")

    result = refresh_recent_closed_candles(
        exchange,
        symbol="ETHUSDT",
        data_dir=tmp_path,
        candle_count=4,
        server_now=exchange.server_now,
    )

    repaired = load_stored_candles(path, now=exchange.server_now, strict=True)
    assert result.bridged_candles > 0
    assert repaired.report.gap_count == 0
    assert repaired.frame.index.equals(
        pd.date_range("2026-06-29T11:15:00Z", "2026-06-29T13:00:00Z", freq="15min")
    )


def test_binance_fresh_install_pages_from_locked_anchor_not_rolling_window(
    tmp_path: Path,
) -> None:
    exchange = _FakeBinance(server_now="2026-06-29T12:52:00Z")

    result = refresh_recent_closed_candles(
        exchange,
        symbol="ETHUSDT",
        data_dir=tmp_path,
        candle_count=4,
        server_now=exchange.server_now,
    )

    assert exchange.calls[0][1] == int(FEATURE_ANCHOR_M15_OPEN.timestamp() * 1_000)
    assert result.requested_fetch_open_at == FEATURE_ANCHOR_M15_OPEN.isoformat()
    assert result.recent_candles == 4
    assert result.total_candles == 6
    loaded = load_stored_candles(
        tmp_path / "ETHUSDT_15m.csv",
        now=exchange.server_now,
        strict=True,
    )
    assert loaded.frame.iloc[0]["open_at"] == pd.Timestamp(FEATURE_ANCHOR_M15_OPEN)


def test_binance_refresh_refuses_existing_file_that_lost_anchor(tmp_path: Path) -> None:
    path = tmp_path / "ETHUSDT_15m.csv"
    rolling_local = (
        pd.Timestamp(FEATURE_ANCHOR_M15_OPEN)
        + pd.Timedelta(hours=7, minutes=15)
    ).tz_localize(None)
    _stored_rows(start=rolling_local.isoformat(), periods=2).to_csv(path, index=False)
    original = path.read_bytes()
    exchange = _FakeBinance(server_now="2026-06-29T12:22:00Z")

    with pytest.raises(BinanceDataError, match="re-anchor migration"):
        refresh_recent_closed_candles(
            exchange,
            symbol="ETHUSDT",
            data_dir=tmp_path,
            candle_count=4,
            server_now=exchange.server_now,
        )

    assert exchange.calls == []
    assert path.read_bytes() == original


def test_binance_refresh_holds_boundary_until_finalization_delay(tmp_path: Path) -> None:
    exchange = _FakeBinance(server_now="2026-06-29T12:15:02Z")

    result = refresh_recent_closed_candles(
        exchange,
        symbol="ETHUSDT",
        data_dir=tmp_path,
        candle_count=4,
        server_now=exchange.server_now,
    )

    assert result.last_closed_at == "2026-06-29T12:00:00+00:00"


@pytest.mark.parametrize("fetch_result", [None, RuntimeError("time endpoint down")])
def test_binance_acquisition_fails_closed_without_authoritative_clock(
    fetch_result,
) -> None:
    class _ClocklessExchange:
        milliseconds_called = False

        def fetch_time(self):
            if isinstance(fetch_result, Exception):
                raise fetch_result
            return fetch_result

        def milliseconds(self):
            self.milliseconds_called = True
            return 1_000

    exchange = _ClocklessExchange()
    with pytest.raises(BinanceDataError, match="authoritative server time"):
        resolve_server_now(exchange)
    assert not exchange.milliseconds_called


def test_binance_acquisition_requires_callable_fetch_time() -> None:
    class _NoFetchTime:
        def milliseconds(self):
            raise AssertionError("local CCXT clock must not be used")

    with pytest.raises(BinanceDataError, match="fetch_time is not callable"):
        resolve_server_now(_NoFetchTime())

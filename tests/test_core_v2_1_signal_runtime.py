from __future__ import annotations

import sqlite3
import threading
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pandas as pd
import pytest

from app.signal.core_v2_1.buffer import (
    ClosedCandleBuffer,
    MarketDataIntegrityError,
    PointInTimeBundleBuilder,
)
from app.signal.core_v2_1.coordinator import (
    CoreV21SignalCoordinator,
    RuntimeEvaluation,
)
from app.signal.core_v2_1.hyperliquid_export import (
    PUMP_FILENAME,
    HyperliquidExportError,
    export_latest_pump_m15,
    load_anchored_pump_m15_seed,
)
from app.signal.core_v2_1.market_data import (
    DEFAULT_FINALIZATION_DELAY,
    BinancePublicCandleSource,
    CompositeMarketDataRouter,
    HyperliquidPublicCandleSource,
    MarketDataSourceError,
    PollCycleError,
    ReconnectingClosedCandlePoller,
    _AuthoritativeClockCache,
)
from app.signal.core_v2_1.market_plan import build_core_v2_1_market_plan
from app.signal.core_v2_1.models import (
    AdvisoryEvent,
    AdvisoryEventType,
    BundleRequirement,
    ClosedCandle,
    MarketKey,
    MarketPlan,
    TriggerPlan,
    Venue,
)
from app.signal.core_v2_1.outbox import DurableOutboxDispatcher, DurableOutboxWorker
from app.signal.core_v2_1.state_store import (
    CoreV21StateStore,
    FeatureAnchorMigrationRequired,
    OutboxLeaseLostError,
)
from app.trading.strategy.core_v2_1 import (
    FEATURE_ANCHOR_M15_OPEN,
    FEATURE_ANCHOR_VERSION,
    INSTRUMENTS,
    TRADE_CANDIDATES,
)


def _dt(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 1, 1, hour, minute, tzinfo=UTC)


def _key(
    instrument: str,
    timeframe: str,
    venue: Venue = Venue.BINANCE_FUTURES,
) -> MarketKey:
    return MarketKey(venue, instrument, timeframe)


def _candle(key: MarketKey, close_time: datetime, price: str = "100") -> ClosedCandle:
    duration = {
        "15m": timedelta(minutes=15),
        "1h": timedelta(hours=1),
        "4h": timedelta(hours=4),
    }[key.timeframe]
    value = Decimal(price)
    return ClosedCandle(
        key=key,
        open_time=close_time - duration,
        close_time=close_time,
        open=value,
        high=value + 1,
        low=value - 1,
        close=value,
        volume=Decimal("10"),
    )


@dataclass(frozen=True)
class _FakeState:
    count: int = 0


class _FakeEvaluator:
    def initial_state(self) -> _FakeState:
        return _FakeState()

    def evaluate(self, bundle, strategy_symbol, state):
        event = AdvisoryEvent(
            event_type=AdvisoryEventType.WAIT_EXPIRED,
            symbol=strategy_symbol,
            venue=bundle.trigger_key.venue,
            closed_at=bundle.as_of,
            wait_elapsed=4,
        )
        return RuntimeEvaluation(
            next_state=_FakeState(state.count + 1),
            decision_kind="WAIT_EXPIRED",
            event=event,
            decision_payload={"count": state.count + 1},
        )

    def dump_state(self, state: _FakeState) -> Mapping[str, Any]:
        return {"count": state.count}

    def load_state(self, payload: Mapping[str, Any]) -> _FakeState:
        return _FakeState(int(payload["count"]))


def _small_plan() -> tuple[MarketPlan, dict[str, MarketKey]]:
    alt_m15 = _key("ETH/USDT:USDT", "15m")
    alt_h1 = _key("ETH/USDT:USDT", "1h")
    btc_h1 = _key("BTC/USDT:USDT", "1h")
    btc_h4 = _key("BTC/USDT:USDT", "4h")
    trigger = TriggerPlan(
        strategy_symbol="ETHUSDT",
        trigger=alt_m15,
        requirements=(
            BundleRequirement(alt_m15, 1, timedelta(0)),
            BundleRequirement(alt_h1, 1, timedelta(hours=1)),
            BundleRequirement(btc_h1, 1, timedelta(hours=1)),
            BundleRequirement(btc_h4, 1, timedelta(hours=4)),
        ),
    )
    return MarketPlan((trigger,)), {
        "m15": alt_m15,
        "alt_h1": alt_h1,
        "btc_h1": btc_h1,
        "btc_h4": btc_h4,
    }


def _seed_for_1145(buffer: ClosedCandleBuffer, keys: dict[str, MarketKey]) -> None:
    buffer.add(_candle(keys["m15"], _dt(11, 45)))
    buffer.add(_candle(keys["alt_h1"], _dt(11)))
    buffer.add(_candle(keys["btc_h1"], _dt(11)))
    buffer.add(_candle(keys["btc_h4"], _dt(8)))


def test_bundle_is_point_in_time_and_requires_exact_utc_boundary() -> None:
    plan, keys = _small_plan()
    buffer = ClosedCandleBuffer()
    buffer.add_many(
        (
            _candle(keys["m15"], _dt(12)),
            _candle(keys["alt_h1"], _dt(11)),
            _candle(keys["alt_h1"], _dt(13)),
            _candle(keys["btc_h1"], _dt(12)),
            _candle(keys["btc_h4"], _dt(12)),
        )
    )

    with pytest.raises(MarketDataIntegrityError, match="boundary is incomplete"):
        PointInTimeBundleBuilder(buffer).build(plan.triggers[0], _dt(12))

    buffer.add(_candle(keys["alt_h1"], _dt(12)))
    bundle = PointInTimeBundleBuilder(buffer).build(plan.triggers[0], _dt(12))
    assert bundle.for_key(keys["alt_h1"]).latest.close_time == _dt(12)
    assert all(
        candle.close_time <= bundle.as_of
        for series in bundle.series
        for candle in series.candles
    )


def test_bundle_rejects_history_gap() -> None:
    plan, keys = _small_plan()
    trigger = TriggerPlan(
        strategy_symbol="ETHUSDT",
        trigger=keys["m15"],
        requirements=(BundleRequirement(keys["m15"], 2, timedelta(0)),),
    )
    buffer = ClosedCandleBuffer()
    buffer.add(_candle(keys["m15"], _dt(11, 30)))
    buffer.add(_candle(keys["m15"], _dt(12)))
    with pytest.raises(MarketDataIntegrityError, match="Gap"):
        PointInTimeBundleBuilder(buffer).build(trigger, _dt(12))
    assert plan.trigger_keys == {keys["m15"]}


def test_silent_bootstrap_restart_and_duplicate_event_are_safe(tmp_path: Path) -> None:
    plan, keys = _small_plan()
    buffer = ClosedCandleBuffer()
    _seed_for_1145(buffer, keys)
    store = CoreV21StateStore(tmp_path / "runtime.sqlite3")
    coordinator = CoreV21SignalCoordinator(
        strategy_version="core-v2.1-test-locked",
        market_plan=plan,
        buffer=buffer,
        store=store,
        evaluator=_FakeEvaluator(),
        topic_by_symbol={"ETHUSDT": 42},
    )

    report = coordinator.bootstrap()[0]
    assert report.evaluated == 1
    assert store.outbox_counts() == {}

    # Restart before the next close.  The cursor and typed state are recovered.
    restarted = CoreV21SignalCoordinator(
        strategy_version="core-v2.1-test-locked",
        market_plan=plan,
        buffer=buffer,
        store=store,
        evaluator=_FakeEvaluator(),
        topic_by_symbol={"ETHUSDT": 42},
    )
    restarted.bootstrap()
    restarted.on_closed_candle(_candle(keys["m15"], _dt(12)))
    restarted.on_closed_candle(_candle(keys["alt_h1"], _dt(12)))
    restarted.on_closed_candle(_candle(keys["btc_h1"], _dt(12)))
    restarted.on_closed_candle(_candle(keys["btc_h4"], _dt(12)))

    assert store.outbox_counts() == {"pending": 1}
    assert store.transition_times("core-v2.1-test-locked", keys["m15"]) == (
        _dt(11, 45),
        _dt(12),
    )

    # Replayed duplicate data and another restart cannot enqueue a second row.
    restarted.on_closed_candle(_candle(keys["m15"], _dt(12)))
    second_restart = CoreV21SignalCoordinator(
        strategy_version="core-v2.1-test-locked",
        market_plan=plan,
        buffer=buffer,
        store=store,
        evaluator=_FakeEvaluator(),
    )
    assert second_restart.bootstrap().ready
    assert store.outbox_counts() == {"pending": 1}


def test_bootstrap_rejects_empty_and_incomplete_history(tmp_path: Path) -> None:
    plan, keys = _small_plan()
    empty = CoreV21SignalCoordinator(
        strategy_version="empty",
        market_plan=plan,
        buffer=ClosedCandleBuffer(),
        store=CoreV21StateStore(tmp_path / "empty.sqlite3"),
        evaluator=_FakeEvaluator(),
    )
    status = empty.bootstrap()
    assert not status.ready
    assert any("no durable cursor" in reason for reason in status.missing_or_blocked)
    with pytest.raises(RuntimeError, match="bootstrap must complete"):
        empty.on_closed_candle(_candle(keys["m15"], _dt(12)))

    incomplete_buffer = ClosedCandleBuffer()
    incomplete_buffer.add(_candle(keys["m15"], _dt(12)))
    incomplete = CoreV21SignalCoordinator(
        strategy_version="incomplete",
        market_plan=plan,
        buffer=incomplete_buffer,
        store=CoreV21StateStore(tmp_path / "incomplete.sqlite3"),
        evaluator=_FakeEvaluator(),
    )
    status = incomplete.bootstrap()
    assert not status.ready
    assert not incomplete.is_ready


def test_bootstrap_retry_keeps_original_history_suppressed(tmp_path: Path) -> None:
    plan, keys = _small_plan()
    buffer = ClosedCandleBuffer()
    _seed_for_1145(buffer, keys)
    buffer.add(_candle(keys["m15"], _dt(12)))
    store = CoreV21StateStore(tmp_path / "partial.sqlite3")
    coordinator = CoreV21SignalCoordinator(
        strategy_version="partial",
        market_plan=plan,
        buffer=buffer,
        store=store,
        evaluator=_FakeEvaluator(),
    )

    first = coordinator.bootstrap()
    assert not first.ready
    assert store.transition_times("partial", keys["m15"]) == (_dt(11, 45),)
    assert store.outbox_counts() == {}

    # Dependencies arrive while startup is still fail-closed.  Retrying the
    # same original bootstrap watermark must not turn its event into an alert.
    buffer.add(_candle(keys["alt_h1"], _dt(12)))
    buffer.add(_candle(keys["btc_h1"], _dt(12)))
    buffer.add(_candle(keys["btc_h4"], _dt(12)))
    # Simulate a process crash/restart after the first suppressed transition.
    restarted = CoreV21SignalCoordinator(
        strategy_version="partial",
        market_plan=plan,
        buffer=buffer,
        store=store,
        evaluator=_FakeEvaluator(),
    )
    second = restarted.bootstrap()
    assert second.ready
    assert store.transition_times("partial", keys["m15"]) == (_dt(11, 45), _dt(12))
    assert store.outbox_counts() == {}


def test_restart_with_cursor_but_missing_dependencies_is_not_ready(tmp_path: Path) -> None:
    plan, keys = _small_plan()
    full = ClosedCandleBuffer()
    _seed_for_1145(full, keys)
    store = CoreV21StateStore(tmp_path / "restart.sqlite3")
    first = CoreV21SignalCoordinator(
        strategy_version="restart",
        market_plan=plan,
        buffer=full,
        store=store,
        evaluator=_FakeEvaluator(),
    )
    assert first.bootstrap().ready

    missing_dependencies = ClosedCandleBuffer()
    missing_dependencies.add(_candle(keys["m15"], _dt(11, 45)))
    restarted = CoreV21SignalCoordinator(
        strategy_version="restart",
        market_plan=plan,
        buffer=missing_dependencies,
        store=store,
        evaluator=_FakeEvaluator(),
    )
    status = restarted.bootstrap()
    assert not status.ready
    assert status.missing_or_blocked


def test_chronological_catchup_does_not_jump_over_missing_m15(tmp_path: Path) -> None:
    plan, keys = _small_plan()
    initial = ClosedCandleBuffer()
    _seed_for_1145(initial, keys)
    store = CoreV21StateStore(tmp_path / "runtime.sqlite3")
    first = CoreV21SignalCoordinator(
        strategy_version="locked",
        market_plan=plan,
        buffer=initial,
        store=store,
        evaluator=_FakeEvaluator(),
    )
    first.bootstrap()

    recovered = ClosedCandleBuffer()
    recovered.add_many(
        (
            _candle(keys["m15"], _dt(12, 15)),
            _candle(keys["alt_h1"], _dt(12)),
            _candle(keys["btc_h1"], _dt(12)),
            _candle(keys["btc_h4"], _dt(12)),
        )
    )
    restart = CoreV21SignalCoordinator(
        strategy_version="locked",
        market_plan=plan,
        buffer=recovered,
        store=store,
        evaluator=_FakeEvaluator(),
    )
    report = restart.bootstrap()[0]
    assert report.evaluated == 0
    assert "chronological catch-up gap" in (report.blocked_reason or "")
    assert store.transition_times("locked", keys["m15"]) == (_dt(11, 45),)


class _FakeResponse:
    def __init__(self, rows, headers=None):
        self._rows = rows
        self.headers = headers or {}

    def raise_for_status(self):
        return None

    def json(self):
        return self._rows


class _FakeSession:
    def __init__(self, rows, headers=None):
        self.rows = rows
        self.headers = headers or {}
        self.calls = []

    def post(self, url, *, json, timeout):
        self.calls.append((url, json, timeout))
        return _FakeResponse(self.rows, self.headers)


def _hyper_row(open_time: datetime, close: str) -> dict[str, str | int]:
    return {
        "t": int(open_time.timestamp() * 1000),
        "o": close,
        "h": str(Decimal(close) + 1),
        "l": str(Decimal(close) - 1),
        "c": close,
        "v": "20",
    }


def test_hyperliquid_public_source_is_credential_free_and_drops_forming_candle() -> None:
    rows = [
        _hyper_row(_dt(11, 15), "100"),
        _hyper_row(_dt(11, 30), "101"),
        _hyper_row(_dt(11, 45), "102"),
        _hyper_row(_dt(12), "103"),  # closes at 12:15, still forming
    ]
    session = _FakeSession(rows)
    source = HyperliquidPublicCandleSource(
        session=session,
        clock=lambda: _dt(12, 7),
    )
    key = _key("PUMP/USDC:USDC", "15m", Venue.HYPERLIQUID_PERP)
    candles = source.fetch_closed(key, _dt(11, 30), _dt(12, 7))

    assert tuple(candle.close_time for candle in candles) == (
        _dt(11, 30),
        _dt(11, 45),
        _dt(12),
    )
    request = session.calls[0][1]
    assert request["type"] == "candleSnapshot"
    assert request["req"]["coin"] == "PUMP"
    assert not any("key" in name.lower() or "wallet" in name.lower() for name in vars(source))


def test_hyperliquid_source_fails_on_retention_truncation() -> None:
    session = _FakeSession([_hyper_row(_dt(11, 15), "100")])
    source = HyperliquidPublicCandleSource(session=session, clock=lambda: _dt(12))
    key = _key("PUMP/USDC:USDC", "15m", Venue.HYPERLIQUID_PERP)
    with pytest.raises(MarketDataSourceError, match="predates Hyperliquid retained coverage"):
        source.fetch_closed(key, _dt(10), _dt(12))


def test_hyperliquid_source_rejects_conflicting_duplicate_close() -> None:
    first = _hyper_row(_dt(11, 45), "100")
    conflicting = {**first, "c": "100.5"}
    source = HyperliquidPublicCandleSource(
        session=_FakeSession([first, conflicting]),
        clock=lambda: _dt(12, 7),
    )
    key = _key("PUMP/USDC:USDC", "15m", Venue.HYPERLIQUID_PERP)

    with pytest.raises(MarketDataSourceError, match="conflicting duplicate"):
        source.fetch_closed(key, _dt(12), _dt(12))


def test_hyperliquid_source_safely_deduplicates_identical_close() -> None:
    row = _hyper_row(_dt(11, 45), "100")
    source = HyperliquidPublicCandleSource(
        session=_FakeSession([row, dict(row)]),
        clock=lambda: _dt(12, 7),
    )
    key = _key("PUMP/USDC:USDC", "15m", Venue.HYPERLIQUID_PERP)

    assert len(source.fetch_closed(key, _dt(12), _dt(12))) == 1


def test_hyperliquid_server_time_uses_public_http_date_header() -> None:
    session = _FakeSession([], {"Date": "Thu, 01 Jan 2026 12:07:00 GMT"})
    source = HyperliquidPublicCandleSource(session=session)
    assert source.resolve_server_now() == _dt(12, 7)
    assert session.calls[0][1] == {"type": "meta"}


def test_hyperliquid_export_round_trips_canonical_csv_and_manifest(tmp_path: Path) -> None:
    anchor = FEATURE_ANCHOR_M15_OPEN
    rows = [
        _hyper_row(anchor, "100"),
        _hyper_row(anchor + timedelta(minutes=15), "101"),
        _hyper_row(anchor + timedelta(minutes=30), "102"),
        _hyper_row(anchor + timedelta(minutes=45), "103"),
    ]
    server_now = anchor + timedelta(hours=1, seconds=7)
    source = HyperliquidPublicCandleSource(
        session=_FakeSession(rows),
        clock=lambda: server_now,
    )
    manifest = tmp_path / "pump-manifest.json"
    result = export_latest_pump_m15(
        source,
        data_dir=tmp_path,
        candle_count=4,
        server_now=server_now,
        manifest_path=manifest,
    )

    assert result.path.name == PUMP_FILENAME
    assert result.venue_instrument == "PUMP/USDC:USDC"
    assert result.row_count == 4
    stored = pd.read_csv(result.path)
    assert list(stored.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert stored.iloc[0]["timestamp"] == "2026-06-29 18:15:00"
    assert manifest.is_file()
    assert result.sha256


def test_pump_seed_loader_preserves_exact_decimal_and_locked_provenance(
    tmp_path: Path,
) -> None:
    anchor_local = (
        pd.Timestamp(FEATURE_ANCHOR_M15_OPEN) + pd.Timedelta(hours=7)
    ).tz_localize(None)
    pd.DataFrame(
        {
            "timestamp": [anchor_local, anchor_local + pd.Timedelta(minutes=15)],
            "open": ["0.123456789123456789", "0.223456789123456789"],
            "high": ["0.2", "0.3"],
            "low": ["0.1", "0.2"],
            "close": ["0.15", "0.25"],
            "volume": ["123.000000000000001", "124.000000000000001"],
        }
    ).to_csv(tmp_path / PUMP_FILENAME, index=False)

    candles = load_anchored_pump_m15_seed(
        tmp_path,
        through=FEATURE_ANCHOR_M15_OPEN + timedelta(minutes=30),
    )

    assert candles[0].key == _key(
        "PUMP/USDC:USDC",
        "15m",
        Venue.HYPERLIQUID_PERP,
    )
    assert candles[0].open == Decimal("0.123456789123456789")
    assert candles[0].volume == Decimal("123.000000000000001")


def test_pump_seed_loader_fails_closed_when_anchor_is_missing(tmp_path: Path) -> None:
    first_local = (
        pd.Timestamp(FEATURE_ANCHOR_M15_OPEN)
        + pd.Timedelta(hours=7, minutes=15)
    ).tz_localize(None)
    pd.DataFrame(
        {
            "timestamp": [first_local],
            "open": ["1"],
            "high": ["2"],
            "low": ["0.5"],
            "close": ["1.5"],
            "volume": ["10"],
        }
    ).to_csv(tmp_path / PUMP_FILENAME, index=False)

    with pytest.raises(HyperliquidExportError, match="locked feature anchor"):
        load_anchored_pump_m15_seed(
            tmp_path,
            through=FEATURE_ANCHOR_M15_OPEN + timedelta(hours=1),
        )


def test_hyperliquid_export_preserves_anchor_and_extends_verified_tail(
    tmp_path: Path,
) -> None:
    anchor = FEATURE_ANCHOR_M15_OPEN
    initial_rows = [
        _hyper_row(anchor + timedelta(minutes=15 * index), str(100 + index))
        for index in range(4)
    ]
    initial_now = anchor + timedelta(hours=1, seconds=7)
    first = export_latest_pump_m15(
        HyperliquidPublicCandleSource(
            session=_FakeSession(initial_rows),
            clock=lambda: initial_now,
        ),
        data_dir=tmp_path,
        candle_count=4,
        server_now=initial_now,
    )
    original = pd.read_csv(first.path, dtype="string")

    extension_rows = [
        _hyper_row(anchor + timedelta(minutes=45), "103"),
        _hyper_row(anchor + timedelta(minutes=60), "104"),
        _hyper_row(anchor + timedelta(minutes=75), "105"),
    ]
    extension_now = anchor + timedelta(hours=1, minutes=30, seconds=7)
    second = export_latest_pump_m15(
        HyperliquidPublicCandleSource(
            session=_FakeSession(extension_rows),
            clock=lambda: extension_now,
        ),
        data_dir=tmp_path,
        candle_count=4,
        server_now=extension_now,
    )
    extended = pd.read_csv(second.path, dtype="string")

    assert second.row_count == 6
    pd.testing.assert_frame_equal(extended.iloc[:4].reset_index(drop=True), original)
    assert second.first_open_utc == FEATURE_ANCHOR_M15_OPEN


def test_hyperliquid_fresh_install_fails_after_anchor_leaves_retention(
    tmp_path: Path,
) -> None:
    server_now = FEATURE_ANCHOR_M15_OPEN + timedelta(
        minutes=15 * 5_001,
        seconds=7,
    )
    source = HyperliquidPublicCandleSource(
        session=_FakeSession([]),
        clock=lambda: server_now,
    )

    with pytest.raises(HyperliquidExportError, match="re-anchor migration"):
        export_latest_pump_m15(
            source,
            data_dir=tmp_path,
            candle_count=5_000,
            server_now=server_now,
        )


class _RouterSource:
    def __init__(
        self,
        venue: Venue,
        rows_by_key: dict[MarketKey, tuple[ClosedCandle, ...]],
        *,
        server_now: datetime | None = None,
    ):
        self.venue = venue
        self.rows_by_key = rows_by_key
        self.server_now = server_now or _dt(12, 1)

    def resolve_server_now(self):
        return self.server_now

    def fetch_closed(self, key, start_close, end_close):
        return self.rows_by_key.get(key, ())


def test_poll_cycle_emits_slow_dependencies_before_colocated_trigger() -> None:
    plan, keys = _small_plan()
    rows = {
        keys["m15"]: (_candle(keys["m15"], _dt(12)),),
        keys["alt_h1"]: (_candle(keys["alt_h1"], _dt(12)),),
        keys["btc_h1"]: (_candle(keys["btc_h1"], _dt(12)),),
        keys["btc_h4"]: (_candle(keys["btc_h4"], _dt(12)),),
    }
    router = CompositeMarketDataRouter(
        (_RouterSource(Venue.BINANCE_FUTURES, rows),)
    )
    emitted: list[MarketKey] = []
    poller = ReconnectingClosedCandlePoller(
        router,
        plan.all_keys,
        lambda candle: emitted.append(candle.key),
        clock=lambda: _dt(12, 1),
    )
    assert poller.poll_once() == 4
    assert [key.timeframe for key in emitted] == ["4h", "1h", "1h", "15m"]


def test_poll_cycle_boundary_order_produces_exactly_one_evaluation(tmp_path: Path) -> None:
    plan, keys = _small_plan()
    buffer = ClosedCandleBuffer()
    _seed_for_1145(buffer, keys)
    store = CoreV21StateStore(tmp_path / "runtime.sqlite3")
    coordinator = CoreV21SignalCoordinator(
        strategy_version="locked-boundary-test",
        market_plan=plan,
        buffer=buffer,
        store=store,
        evaluator=_FakeEvaluator(),
    )
    coordinator.bootstrap()

    rows = {
        keys["m15"]: (_candle(keys["m15"], _dt(12)),),
        keys["alt_h1"]: (_candle(keys["alt_h1"], _dt(12)),),
        keys["btc_h1"]: (_candle(keys["btc_h1"], _dt(12)),),
        keys["btc_h4"]: (_candle(keys["btc_h4"], _dt(12)),),
    }
    poller = ReconnectingClosedCandlePoller(
        CompositeMarketDataRouter((_RouterSource(Venue.BINANCE_FUTURES, rows),)),
        plan.all_keys,
        lambda candle: coordinator.on_closed_candle(candle),
        clock=lambda: _dt(12, 1),
    )

    assert poller.poll_once() == 4
    assert store.transition_times("locked-boundary-test", keys["m15"]) == (
        _dt(11, 45),
        _dt(12),
    )
    assert store.outbox_counts() == {"pending": 1}


def test_poll_cycle_keeps_cursor_before_gap() -> None:
    key = _key("ETH/USDT:USDT", "15m")
    source = _RouterSource(
        Venue.BINANCE_FUTURES,
        {key: (_candle(key, _dt(12, 15)),)},
    )
    emitted = []
    poller = ReconnectingClosedCandlePoller(
        CompositeMarketDataRouter((source,)),
        (key,),
        emitted.append,
        clock=lambda: _dt(12, 16),
    )
    poller.seed_cursor(key, _dt(11, 45))
    with pytest.raises(PollCycleError, match="expected"):
        poller.poll_once()
    assert emitted == []


def test_poll_cycle_rejects_stale_overlap_only_response() -> None:
    key = _key("ETH/USDT:USDT", "15m")
    source = _RouterSource(
        Venue.BINANCE_FUTURES,
        {key: (_candle(key, _dt(12)),)},
    )
    emitted: list[ClosedCandle] = []
    poller = ReconnectingClosedCandlePoller(
        CompositeMarketDataRouter((source,)),
        (key,),
        emitted.append,
        clock=lambda: _dt(12, 16),
    )
    poller.seed_cursor(key, _dt(12))

    with pytest.raises(PollCycleError, match="tail is stale"):
        poller.poll_once()
    assert emitted == []
    assert not poller.is_ready


def test_poll_cycle_retries_same_candle_after_callback_failure() -> None:
    key = _key("ETH/USDT:USDT", "15m")
    source = _RouterSource(
        Venue.BINANCE_FUTURES,
        {key: (_candle(key, _dt(12)),)},
    )
    attempts: list[ClosedCandle] = []

    def flaky_callback(candle: ClosedCandle) -> None:
        attempts.append(candle)
        if len(attempts) == 1:
            raise RuntimeError("sqlite temporarily busy")

    poller = ReconnectingClosedCandlePoller(
        CompositeMarketDataRouter((source,)),
        (key,),
        flaky_callback,
        clock=lambda: _dt(12, 1),
    )
    with pytest.raises(PollCycleError, match="callback failed"):
        poller.poll_once()
    assert "sqlite temporarily busy" in (poller.last_error or "")
    assert not poller.is_ready

    assert poller.poll_once() == 1
    assert len(attempts) == 2
    assert poller.is_ready
    assert poller.last_error is None


def test_poller_stop_timeout_cannot_report_a_false_restart(monkeypatch) -> None:
    key = _key("ETH/USDT:USDT", "15m")
    poller = ReconnectingClosedCandlePoller(
        CompositeMarketDataRouter((_RouterSource(Venue.BINANCE_FUTURES, {}),)),
        (key,),
        lambda candle: None,
        poll_interval_seconds=0.01,
        clock=lambda: _dt(12, 1),
    )
    entered = threading.Event()
    release = threading.Event()

    def blocking_poll() -> int:
        entered.set()
        release.wait(timeout=2)
        return 0

    monkeypatch.setattr(poller, "poll_once", blocking_poll)
    poller.start()
    assert entered.wait(timeout=1)
    with pytest.raises(TimeoutError, match="did not stop"):
        poller.stop(timeout_seconds=0.001)
    with pytest.raises(RuntimeError, match="shutdown is still in progress"):
        poller.start()

    release.set()
    poller.stop(timeout_seconds=1)
    poller.start()
    poller.stop(timeout_seconds=1)


def test_outbox_worker_stop_timeout_cannot_report_a_false_restart() -> None:
    entered = threading.Event()
    release = threading.Event()

    class _BlockingDispatcher:
        def dispatch_due(self) -> None:
            entered.set()
            release.wait(timeout=2)

    worker = DurableOutboxWorker(_BlockingDispatcher(), interval_seconds=0.01)
    worker.start()
    assert entered.wait(timeout=1)
    with pytest.raises(TimeoutError, match="did not stop"):
        worker.stop(timeout_seconds=0.001)
    with pytest.raises(RuntimeError, match="shutdown is still in progress"):
        worker.start()

    release.set()
    worker.stop(timeout_seconds=1)
    worker.start()
    worker.stop(timeout_seconds=1)


class _FlakySink:
    def __init__(self) -> None:
        self.calls = 0

    def deliver(self, message, *, topic_id, event_id):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("temporary outage")


def test_durable_outbox_retries_and_marks_sent_only_after_success(tmp_path: Path) -> None:
    plan, keys = _small_plan()
    store = CoreV21StateStore(tmp_path / "runtime.sqlite3")
    event = AdvisoryEvent(
        event_type=AdvisoryEventType.WAIT_EXPIRED,
        symbol="ETHUSDT",
        venue=Venue.BINANCE_FUTURES,
        closed_at=_dt(12),
        wait_elapsed=4,
    )
    store.commit_transition(
        strategy_id="locked",
        trigger_key=keys["m15"],
        processed_at=_dt(12),
        expected_last_processed_at=None,
        state_payload={"count": 1},
        decision_kind="WAIT_EXPIRED",
        event=event,
        message="test",
        topic_id=42,
    )
    sink = _FlakySink()
    dispatcher = DurableOutboxDispatcher(
        store,
        sink,
        initial_retry_seconds=5,
        max_retry_seconds=10,
    )

    now = datetime.now(UTC) + timedelta(seconds=1)
    first = dispatcher.dispatch_due(now=now)
    assert first.failed == 1
    assert store.outbox_counts() == {"retry": 1}
    assert dispatcher.dispatch_due(now=now + timedelta(seconds=4)).claimed == 0
    second = dispatcher.dispatch_due(now=now + timedelta(seconds=5))
    assert second.sent == 1
    assert store.outbox_counts() == {"sent": 1}


def test_durable_outbox_caps_retry_before_large_exponent(tmp_path: Path) -> None:
    _plan, keys = _small_plan()
    store = CoreV21StateStore(tmp_path / "runtime.sqlite3")
    event = AdvisoryEvent(
        event_type=AdvisoryEventType.WAIT_EXPIRED,
        symbol="ETHUSDT",
        venue=Venue.BINANCE_FUTURES,
        closed_at=_dt(12),
        wait_elapsed=4,
    )
    store.commit_transition(
        strategy_id="locked",
        trigger_key=keys["m15"],
        processed_at=_dt(12),
        expected_last_processed_at=None,
        state_payload={"count": 1},
        decision_kind="WAIT_EXPIRED",
        event=event,
        message="test",
    )
    with sqlite3.connect(store.path) as connection:
        connection.execute(
            "UPDATE core_v2_notification_outbox SET attempts = 2048"
        )

    class _AlwaysFailSink:
        def deliver(self, message, *, topic_id, event_id):
            raise RuntimeError("persistent outage")

    dispatcher = DurableOutboxDispatcher(
        store,
        _AlwaysFailSink(),
        initial_retry_seconds=5,
        max_retry_seconds=300,
    )
    now = datetime.now(UTC) + timedelta(seconds=1)
    summary = dispatcher.dispatch_due(now=now)
    assert summary.failed == 1
    with sqlite3.connect(store.path) as connection:
        attempts, retry_at = connection.execute(
            "SELECT attempts, next_attempt_at FROM core_v2_notification_outbox"
        ).fetchone()
    assert attempts == 2049
    assert datetime.fromisoformat(retry_at) == now + timedelta(seconds=300)


def test_expired_outbox_lease_cannot_be_acknowledged_by_stale_dispatcher(
    tmp_path: Path,
) -> None:
    _plan, keys = _small_plan()
    store = CoreV21StateStore(tmp_path / "runtime.sqlite3")
    event = AdvisoryEvent(
        event_type=AdvisoryEventType.WAIT_EXPIRED,
        symbol="ETHUSDT",
        venue=Venue.BINANCE_FUTURES,
        closed_at=_dt(12),
        wait_elapsed=4,
    )
    store.commit_transition(
        strategy_id="locked",
        trigger_key=keys["m15"],
        processed_at=_dt(12),
        expected_last_processed_at=None,
        state_payload={"count": 1},
        decision_kind="WAIT_EXPIRED",
        event=event,
        message="test",
        topic_id=42,
    )
    now = datetime.now(UTC) + timedelta(seconds=1)
    first = store.claim_due_outbox(now=now, lease_seconds=1)
    second = store.claim_due_outbox(now=now + timedelta(seconds=2), lease_seconds=30)

    assert len(first) == len(second) == 1
    assert first[0].claim_token != second[0].claim_token
    with pytest.raises(OutboxLeaseLostError, match="no longer owned"):
        store.mark_outbox_sent(
            first[0].outbox_id,
            claim_token=first[0].claim_token,
            sent_at=now + timedelta(seconds=3),
        )
    store.mark_outbox_sent(
        second[0].outbox_id,
        claim_token=second[0].claim_token,
        sent_at=now + timedelta(seconds=3),
    )
    assert store.outbox_counts() == {"sent": 1}


def test_market_plan_is_derived_from_locked_core_universe() -> None:
    plan = build_core_v2_1_market_plan()
    by_symbol = {trigger.strategy_symbol: trigger for trigger in plan.triggers}

    assert tuple(by_symbol) == TRADE_CANDIDATES
    assert len(plan.trigger_keys) == 25
    assert len(plan.dependency_keys) == 27
    for symbol, instrument in INSTRUMENTS.items():
        trigger = by_symbol[symbol]
        assert trigger.trigger.venue is instrument.venue
        assert trigger.trigger.instrument == instrument.venue_symbol
    assert by_symbol["PUMP"].trigger.instrument == "PUMP/USDC:USDC"


class _FakeBinanceExchange:
    def __init__(self, *, server_now: datetime, rows) -> None:
        self.server_now = server_now
        self.rows = rows
        self.fetch_time_calls = 0

    def fetch_time(self):
        self.fetch_time_calls += 1
        return int(self.server_now.timestamp() * 1000)

    def fetch_ohlcv(self, symbol, timeframe, *, since, limit):
        return self.rows


def test_binance_source_uses_server_time_and_finalization_delay_not_host_clock() -> None:
    key = _key("ETH/USDT:USDT", "15m")
    row = [int(_dt(11, 45).timestamp() * 1000), "100", "101", "99", "100", "10"]
    before_finalization = _FakeBinanceExchange(
        server_now=_dt(12, 0) + timedelta(seconds=2),
        rows=(row,),
    )
    source = BinancePublicCandleSource(exchange=before_finalization)
    assert source.fetch_closed(key, _dt(11, 45), _dt(12, 30)) == ()

    after_finalization = _FakeBinanceExchange(
        server_now=_dt(12, 0) + timedelta(seconds=6),
        rows=(row,),
    )
    source = BinancePublicCandleSource(exchange=after_finalization)
    candles = source.fetch_closed(key, _dt(11, 45), _dt(12, 30))
    assert tuple(candle.close_time for candle in candles) == (_dt(12),)
    assert after_finalization.fetch_time_calls == 1


def test_binance_source_rejects_conflicting_duplicate_close() -> None:
    key = _key("ETH/USDT:USDT", "15m")
    open_ms = int(_dt(11, 45).timestamp() * 1000)
    rows = (
        [open_ms, "100", "101", "99", "100", "10"],
        [open_ms, "100", "101", "99", "100.5", "10"],
    )
    source = BinancePublicCandleSource(
        exchange=_FakeBinanceExchange(
            server_now=_dt(12) + timedelta(seconds=6),
            rows=rows,
        )
    )

    with pytest.raises(MarketDataSourceError, match="conflicting duplicate"):
        source.fetch_closed(key, _dt(12), _dt(12))


def test_binance_source_safely_deduplicates_identical_close() -> None:
    key = _key("ETH/USDT:USDT", "15m")
    row = [int(_dt(11, 45).timestamp() * 1000), "100", "101", "99", "100", "10"]
    source = BinancePublicCandleSource(
        exchange=_FakeBinanceExchange(
            server_now=_dt(12) + timedelta(seconds=6),
            rows=(row, list(row)),
        )
    )

    assert len(source.fetch_closed(key, _dt(12), _dt(12))) == 1


def test_composite_watermark_uses_slowest_venue_server_clock() -> None:
    router = CompositeMarketDataRouter(
        (
            _RouterSource(
                Venue.BINANCE_FUTURES,
                {},
                server_now=_dt(12, 0) + timedelta(seconds=20),
            ),
            _RouterSource(
                Venue.HYPERLIQUID_PERP,
                {},
                server_now=_dt(12, 0) + timedelta(seconds=3),
            ),
        )
    )
    assert router.finalized_through() == _dt(11, 59) + timedelta(seconds=58)
    assert DEFAULT_FINALIZATION_DELAY == timedelta(seconds=5)


def test_authoritative_clock_cache_never_double_counts_fetch_latency(monkeypatch) -> None:
    ticks = iter((100.0, 105.0, 106.0))
    monkeypatch.setattr(
        "app.signal.core_v2_1.market_data.time.monotonic",
        lambda: next(ticks),
    )
    fetches = 0

    def slow_fetch() -> datetime:
        nonlocal fetches
        fetches += 1
        return _dt(12)

    cache = _AuthoritativeClockCache(refresh_seconds=30)
    assert cache.resolve(slow_fetch) == _dt(12)
    # The request consumed five monotonic seconds.  The cached clock advances
    # only from response completion, so it is one—not six—seconds ahead.
    assert cache.resolve(slow_fetch) == _dt(12) + timedelta(seconds=1)
    assert fetches == 1


def test_poller_does_not_accept_exact_boundary_before_finalization_delay() -> None:
    key = _key("ETH/USDT:USDT", "15m")
    source = _RouterSource(
        Venue.BINANCE_FUTURES,
        {key: (_candle(key, _dt(12)),)},
        server_now=_dt(12) + timedelta(seconds=2),
    )
    poller = ReconnectingClosedCandlePoller(
        CompositeMarketDataRouter((source,)),
        (key,),
        lambda candle: None,
    )
    with pytest.raises(PollCycleError, match="out-of-window"):
        poller.poll_once()


@pytest.mark.parametrize(
    ("field", "value", "error"),
    (
        ("open", 100.0, TypeError),
        ("close", Decimal("NaN"), ValueError),
        ("low", Decimal("0"), ValueError),
        ("volume", Decimal("Infinity"), ValueError),
    ),
)
def test_closed_candle_rejects_non_decimal_non_finite_or_nonpositive_values(
    field,
    value,
    error,
) -> None:
    key = _key("ETH/USDT:USDT", "15m")
    values = {
        "open": Decimal("100"),
        "high": Decimal("101"),
        "low": Decimal("99"),
        "close": Decimal("100"),
        "volume": Decimal("10"),
    }
    values[field] = value
    with pytest.raises(error):
        ClosedCandle(
            key=key,
            open_time=_dt(11, 45),
            close_time=_dt(12),
            **values,
        )


def test_legacy_state_without_anchor_requires_explicit_migration(tmp_path: Path) -> None:
    database = tmp_path / "legacy.sqlite3"
    key = _key("ETH/USDT:USDT", "15m")
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE core_v2_runtime_state (
                strategy_id TEXT NOT NULL,
                venue TEXT NOT NULL,
                instrument TEXT NOT NULL,
                timeframe TEXT NOT NULL,
                state_json TEXT NOT NULL,
                last_processed_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (strategy_id, venue, instrument, timeframe)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO core_v2_runtime_state (
                strategy_id, venue, instrument, timeframe,
                state_json, last_processed_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "legacy",
                key.venue.value,
                key.instrument,
                key.timeframe,
                "{}",
                _dt(12).isoformat(),
                _dt(12).isoformat(),
            ),
        )
    store = CoreV21StateStore(database)
    with pytest.raises(FeatureAnchorMigrationRequired, match="re-anchor migration"):
        store.load_cursor("legacy", key)


def test_transition_persists_locked_anchor_in_state_and_audit(tmp_path: Path) -> None:
    plan, keys = _small_plan()
    store = CoreV21StateStore(tmp_path / "anchor.sqlite3")
    store.commit_transition(
        strategy_id="anchor-test",
        trigger_key=keys["m15"],
        processed_at=_dt(12),
        expected_last_processed_at=None,
        state_payload={"count": 1},
        decision_kind="NO_EVENT",
    )
    cursor = store.load_cursor("anchor-test", keys["m15"])
    assert cursor is not None
    assert cursor.feature_anchor_version == FEATURE_ANCHOR_VERSION
    assert cursor.feature_anchor_open == FEATURE_ANCHOR_M15_OPEN
    with sqlite3.connect(store.path) as connection:
        row = connection.execute(
            """
            SELECT feature_anchor_version, feature_anchor_open
            FROM core_v2_runtime_transitions
            WHERE strategy_id = 'anchor-test'
            """
        ).fetchone()
    assert row == (FEATURE_ANCHOR_VERSION, FEATURE_ANCHOR_M15_OPEN.isoformat())


def test_live_cli_loads_dotenv_before_building_composition(monkeypatch, tmp_path) -> None:
    import app.signal.core_v2_1.live as live_cli

    calls: list[str] = []

    class _Runtime:
        def start(self):
            calls.append("start")
            return SimpleNamespace(hydrated_candles=0)

        def stop(self):
            calls.append("stop")

    def fake_load_dotenv():
        calls.append("dotenv")
        monkeypatch.setenv("TELEGRAM_CHAT_ID", "-100123")

    def fake_build(**kwargs):
        calls.append("build")
        assert kwargs["telegram_chat_id"] == "-100123"
        assert kwargs["bootstrap_data_dir"] == live_cli.DEFAULT_DATA_DIR
        return _Runtime()

    def fake_signal(signum, handler):
        if signum == live_cli.signal.SIGINT:
            handler(signum, None)

    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setattr(live_cli, "load_dotenv", fake_load_dotenv)
    monkeypatch.setattr(
        live_cli.CoreV21LiveSignalRuntime,
        "with_public_venues_and_telegram",
        staticmethod(fake_build),
    )
    monkeypatch.setattr(live_cli.signal, "signal", fake_signal)

    assert live_cli.main(["--state-db", str(tmp_path / "cli.sqlite3")]) == 0
    assert calls == ["dotenv", "build", "start", "stop"]

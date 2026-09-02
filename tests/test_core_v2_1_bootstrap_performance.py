from __future__ import annotations

import sqlite3
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

import app.signal.core_v2_1.core_adapter as adapter_module
from app.signal.core_v2_1.buffer import (
    ClosedCandleBuffer,
    PointInTimeBundleBuilder,
)
from app.signal.core_v2_1.coordinator import CoreV21SignalCoordinator
from app.signal.core_v2_1.core_adapter import (
    RUNTIME_STRATEGY_VERSION,
    CoreV21RuntimeEvaluator,
)
from app.signal.core_v2_1.market_data import CompositeMarketDataRouter
from app.signal.core_v2_1.market_plan import build_core_v2_1_market_plan
from app.signal.core_v2_1.models import (
    ClosedCandle,
    MarketKey,
    MarketPlan,
    Venue,
    timeframe_delta,
)
from app.signal.core_v2_1.state_store import CoreV21StateStore
from app.trading.strategy.core_v2_1 import first_fully_covered_close

BOOTSTRAP_PERFORMANCE_BUDGET_SECONDS = 35


class _DeterministicSource:
    def __init__(self, venue: Venue) -> None:
        self.venue = venue
        self.calls: list[MarketKey] = []

    def resolve_server_now(self) -> datetime:
        return datetime(2026, 8, 21, tzinfo=UTC)

    def fetch_closed(
        self,
        key: MarketKey,
        start_close: datetime,
        end_close: datetime,
    ) -> tuple[ClosedCandle, ...]:
        assert key.venue is self.venue
        self.calls.append(key)
        duration = timeframe_delta(key.timeframe)
        seconds = int(duration.total_seconds())
        start_seconds = int(start_close.timestamp())
        current = datetime.fromtimestamp(
            ((start_seconds + seconds - 1) // seconds) * seconds,
            tz=UTC,
        )
        last = datetime.fromtimestamp(
            (int(end_close.timestamp()) // seconds) * seconds,
            tz=UTC,
        )
        instrument_seed = sum(ord(character) for character in key.instrument) % 500
        candles: list[ClosedCandle] = []
        while current <= last:
            step = int(
                (
                    current
                    - datetime(2026, 6, 29, 11, 15, tzinfo=UTC)
                ).total_seconds()
                // 900
            )
            close = (
                Decimal("100")
                + Decimal(instrument_seed)
                + Decimal(step) / Decimal("1000")
            )
            candles.append(
                ClosedCandle(
                    key=key,
                    open_time=current - duration,
                    close_time=current,
                    open=close - Decimal("0.03"),
                    high=close + Decimal("0.20"),
                    low=close - Decimal("0.20"),
                    close=close,
                    volume=Decimal("100"),
                )
            )
            current += duration
        return tuple(candles)


def _composition(
    database: Path,
    plan: MarketPlan,
) -> tuple[
    CoreV21SignalCoordinator,
    CoreV21StateStore,
    CoreV21RuntimeEvaluator,
]:
    store = CoreV21StateStore(database)
    evaluator = CoreV21RuntimeEvaluator()
    coordinator = CoreV21SignalCoordinator(
        strategy_version=RUNTIME_STRATEGY_VERSION,
        market_plan=plan,
        buffer=ClosedCandleBuffer(max_candles_per_market=None),
        store=store,
        evaluator=evaluator,
    )
    return coordinator, store, evaluator


def _router() -> tuple[
    CompositeMarketDataRouter,
    _DeterministicSource,
    _DeterministicSource,
]:
    binance = _DeterministicSource(Venue.BINANCE_FUTURES)
    hyperliquid = _DeterministicSource(Venue.HYPERLIQUID_PERP)
    return CompositeMarketDataRouter((binance, hyperliquid)), binance, hyperliquid


def _backup_database(source: Path, destination: Path) -> None:
    with sqlite3.connect(source) as source_connection:
        with sqlite3.connect(destination) as destination_connection:
            source_connection.backup(destination_connection)


def _database_signature(database: Path) -> tuple[tuple[object, ...], ...]:
    with sqlite3.connect(database) as connection:
        transitions = connection.execute(
            """
            SELECT venue, instrument, timeframe, processed_at, decision_kind,
                   decision_json, event_id, notification_suppressed
            FROM core_v2_runtime_transitions
            ORDER BY venue, instrument, timeframe, processed_at
            """
        ).fetchall()
        events = connection.execute(
            """
            SELECT event_id, strategy_symbol, venue, instrument, timeframe,
                   processed_at, event_type, payload_json, notification_suppressed
            FROM core_v2_runtime_events
            ORDER BY event_id
            """
        ).fetchall()
        outbox = connection.execute(
            """
            SELECT event_id, topic_id, message, status, attempts
            FROM core_v2_notification_outbox
            ORDER BY event_id
            """
        ).fetchall()
    return tuple(transitions), tuple(events), tuple(outbox)


def _new_candles(
    plan: MarketPlan,
    sources: dict[Venue, _DeterministicSource],
    start: datetime,
    through: datetime,
) -> tuple[ClosedCandle, ...]:
    result: list[ClosedCandle] = []
    for key in plan.all_keys:
        duration = timeframe_delta(key.timeframe)
        seconds = int(duration.total_seconds())
        latest = datetime.fromtimestamp(
            (int(start.timestamp()) // seconds) * seconds,
            tz=UTC,
        )
        result.extend(
            sources[key.venue].fetch_closed(
                key,
                latest + duration,
                through,
            )
        )
    dependency_order = {"4h": 0, "1h": 1, "15m": 2}
    return tuple(
        sorted(
            result,
            key=lambda candle: (
                candle.close_time,
                dependency_order[candle.key.timeframe],
                candle.key.storage_id,
            ),
        )
    )


def test_full_universe_cold_bootstrap_precomputes_once_and_restart_matches_live(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = build_core_v2_1_market_plan()
    assert len(plan.triggers) == 25
    assert len(plan.all_keys) == 52
    # Exact 5,000-M15 anchored window used by the checked full replay.
    cold_through = datetime(2026, 8, 20, 13, 15, tzinfo=UTC)
    catchup_through = cold_through + timedelta(hours=1)
    uninterrupted_path = tmp_path / "uninterrupted.sqlite3"
    restarted_path = tmp_path / "restarted.sqlite3"
    router, binance, hyperliquid = _router()
    coordinator, store, _evaluator = _composition(uninterrupted_path, plan)

    feature_calls = {
        "compute_m15_indicators": 0,
        "compute_alt_h1_indicators": 0,
        "compute_btc_h1_indicators": 0,
        "compute_btc_h4_indicators": 0,
    }
    for name in tuple(feature_calls):
        original = getattr(adapter_module, name)

        def counted(frame, *, _name=name, _original=original):
            feature_calls[_name] += 1
            return _original(frame)

        monkeypatch.setattr(adapter_module, name, counted)

    batch_sizes: list[int] = []
    original_batch = store.commit_transition_batch

    def counted_batch(**kwargs):
        batch_sizes.append(len(kwargs["transitions"]))
        return original_batch(**kwargs)

    monkeypatch.setattr(store, "commit_transition_batch", counted_batch)
    coordinator.hydrate(router, through=cold_through)
    assert len(binance.calls) == 50
    assert len(hyperliquid.calls) == 2
    assert {key.instrument for key in hyperliquid.calls} == {"PUMP/USDC:USDC"}

    def growing_prefix_build(*args, **kwargs):
        raise AssertionError("prepared bootstrap must not build growing PIT prefixes")

    monkeypatch.setattr(PointInTimeBundleBuilder, "build", growing_prefix_build)
    started = time.perf_counter()
    cold = coordinator.bootstrap(through=cold_through)
    elapsed = time.perf_counter() - started

    assert cold.ready, cold.missing_or_blocked
    # Hosted runners vary materially under the full 25-market workload; keep
    # this as a regression guard while allowing normal CI scheduling jitter.
    assert elapsed < BOOTSTRAP_PERFORMANCE_BUDGET_SECONDS
    assert feature_calls == {
        "compute_m15_indicators": 25,
        "compute_alt_h1_indicators": 25,
        "compute_btc_h1_indicators": 1,
        "compute_btc_h4_indicators": 1,
    }
    assert batch_sizes == [3_942] * 25
    assert all(report.considered == 5_000 for report in cold.reports)
    assert all(report.evaluated == 3_942 for report in cold.reports)
    assert all(report.blocked_reason is None for report in cold.reports)
    assert store.outbox_counts() == {}
    with sqlite3.connect(uninterrupted_path) as connection:
        transition_count, suppressed_count = connection.execute(
            """
            SELECT COUNT(*), SUM(notification_suppressed)
            FROM core_v2_runtime_transitions
            """
        ).fetchone()
    assert (transition_count, suppressed_count) == (98_550, 98_550)
    for trigger in plan.triggers:
        cursor = store.load_cursor(RUNTIME_STRATEGY_VERSION, trigger.trigger)
        assert cursor is not None
        assert cursor.last_processed_at == cold_through

    _backup_database(uninterrupted_path, restarted_path)
    sources = {
        Venue.BINANCE_FUTURES: binance,
        Venue.HYPERLIQUID_PERP: hyperliquid,
    }
    for candle in _new_candles(plan, sources, cold_through, catchup_through):
        coordinator.on_closed_candle(candle)

    restart_router, _restart_binance, _restart_hyperliquid = _router()
    restarted, restarted_store, _ = _composition(restarted_path, plan)
    restarted.hydrate(restart_router, through=catchup_through)
    restart_status = restarted.bootstrap(through=catchup_through)
    assert restart_status.ready, restart_status.missing_or_blocked
    assert all(report.evaluated == 4 for report in restart_status.reports)

    for trigger in plan.triggers:
        uninterrupted_cursor = store.load_cursor(
            RUNTIME_STRATEGY_VERSION,
            trigger.trigger,
        )
        restarted_cursor = restarted_store.load_cursor(
            RUNTIME_STRATEGY_VERSION,
            trigger.trigger,
        )
        assert uninterrupted_cursor is not None
        assert restarted_cursor is not None
        assert restarted_cursor.last_processed_at == catchup_through
        assert restarted_cursor.state_payload == uninterrupted_cursor.state_payload
    assert _database_signature(restarted_path) == _database_signature(
        uninterrupted_path
    )


def test_prepared_history_matches_legacy_prefix_inputs_and_decisions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    full_plan = build_core_v2_1_market_plan()
    eth = next(
        trigger
        for trigger in full_plan.triggers
        if trigger.strategy_symbol == "ETHUSDT"
    )
    plan = MarketPlan((eth,))
    through = datetime(2026, 7, 16, 8, 15, tzinfo=UTC)
    source = _DeterministicSource(Venue.BINANCE_FUTURES)
    buffer = ClosedCandleBuffer(max_candles_per_market=None)
    for key in plan.all_keys:
        buffer.add_many(
            source.fetch_closed(
                key,
                first_fully_covered_close(key.timeframe),
                through,
            )
        )

    evaluator = CoreV21RuntimeEvaluator()
    evaluator.prepare_history(
        tuple(
            buffer.series_as_of(key, through, minimum_candles=1)
            for key in sorted(plan.all_keys)
        )
    )
    captured_inputs = []
    original_evaluate = adapter_module.evaluate_core_v2_1

    def capture_input(evaluation_input, state):
        captured_inputs.append(evaluation_input)
        return original_evaluate(evaluation_input, state)

    monkeypatch.setattr(adapter_module, "evaluate_core_v2_1", capture_input)
    builder = PointInTimeBundleBuilder(buffer)
    legacy_state = evaluator.initial_state()
    prepared_state = evaluator.initial_state()
    closed_at = datetime(2026, 7, 16, 4, tzinfo=UTC)
    compared = 0
    while closed_at <= through:
        legacy = evaluator.evaluate(
            builder.build(eth, closed_at),
            eth.strategy_symbol,
            legacy_state,
        )
        prepared = evaluator.evaluate_prepared(eth, closed_at, prepared_state)
        assert captured_inputs[-2] == captured_inputs[-1]
        assert prepared == legacy
        legacy_state = legacy.next_state
        prepared_state = prepared.next_state
        compared += 1
        closed_at += timedelta(minutes=15)

    assert compared == 18
    assert len(captured_inputs) == compared * 2
    assert prepared_state == legacy_state

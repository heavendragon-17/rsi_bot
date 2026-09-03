"""Focused tests for the BTC M5/M15 signal review dataset and API."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from btc_alert_fixtures import (
    BASE,
    h4_close_times,
    h4_price_above_ema21_closes,
    qualifying_m5_trigger,
    qualifying_trigger,
)
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.main import app
from app.api.routes import signal_replays
from app.api.schemas import SignalHumanOutcome, SignalQuality, SignalReviewUpdate
from app.backtest import signal_replay_service
from app.backtest.signal_replay import run_btc_alert_replay
from app.backtest.signal_replay_analysis import (
    CHART_CHUNK_CANDLES,
    TRADE_EXIT_BOTH_SAME_CANDLE,
    TRADE_EXIT_NO_DATA,
    TRADE_EXIT_OPEN,
    TRADE_EXIT_STOP_LOSS,
    TRADE_EXIT_TAKE_PROFIT,
    calculate_forward_metrics,
    chart_candles,
    chart_window_from_frame,
    evaluate_long_trade,
    prepare_forward_metric_source,
    source_metadata,
)
from app.backtest.signal_replay_data import load_ohlcv_csv
from app.backtest.signal_replay_persistence import build_signal_rows
from app.backtest.signal_replay_service import SignalReplayService
from app.repository.backtest.database import Base
from app.repository.backtest.models import SignalReplayRun, SignalReplaySignal

STORAGE_SHIFT = timedelta(hours=7)


def _write_ohlcv_csv(path, close_times, closes, step):
    frame = pd.DataFrame(
        {
            "timestamp": [
                (close_time - step + STORAGE_SHIFT).replace(tzinfo=None)
                for close_time in close_times
            ],
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": [1.0] * len(closes),
        }
    )
    frame.to_csv(path, index=False)
    if "4h" in path.name:
        h1_path = path.with_name(path.name.replace("4h", "1h"))
        h1_step = timedelta(hours=1)
        h1_end = max(close_times) + timedelta(hours=4)
        h1_times = [
            h1_end - h1_step * (69 - position) for position in range(70)
        ]
        _write_ohlcv_csv(
            h1_path,
            h1_times,
            [100.0 + position for position in range(70)],
            h1_step,
        )


def _write_qualifying_csvs(tmp_path):
    m5_end = BASE.replace(hour=9, minute=45)
    m15_end = BASE.replace(hour=10, minute=0)
    h4_end = BASE.replace(hour=8)
    m5_times, m5_closes = qualifying_m5_trigger(timedelta(minutes=5), m5_end)
    m15_times, m15_closes = qualifying_trigger(timedelta(minutes=15), m15_end)
    h4_times = h4_close_times(h4_end)
    h4_closes = h4_price_above_ema21_closes()

    m5_path = tmp_path / "BTCUSDT_5m.csv"
    m15_path = tmp_path / "BTCUSDT_15m.csv"
    h4_path = tmp_path / "BTCUSDT_4h.csv"
    _write_ohlcv_csv(m5_path, m5_times, m5_closes, timedelta(minutes=5))
    _write_ohlcv_csv(m15_path, m15_times, m15_closes, timedelta(minutes=15))
    _write_ohlcv_csv(h4_path, h4_times, h4_closes, timedelta(hours=4))
    return m5_path, m15_path, h4_path


def _seed_replay(tmp_path, db):
    m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)
    result = run_btc_alert_replay(
        m5_path,
        m15_path,
        h4_path,
        start_utc7=datetime(2026, 8, 24, 16, 40),
        end_utc7=datetime(2026, 8, 24, 17, 10),
        write_output=False,
    )
    m5_frame = load_ohlcv_csv(m5_path, "5m")
    m15_frame = load_ohlcv_csv(m15_path, "15m")
    h1_path = h4_path.with_name(h4_path.name.replace("4h", "1h"))
    h1_frame = load_ohlcv_csv(h1_path, "1h")
    h4_frame = load_ohlcv_csv(h4_path, "4h")
    run = SignalReplayRun(
        status="completed",
        definition_version="btc-rsi-cross-v1",
        symbol="BTC/USDT",
        source_metadata={
            "5m": source_metadata(m5_path, m5_frame, "5m"),
            "15m": source_metadata(m15_path, m15_frame, "15m"),
            "1h": source_metadata(h1_path, h1_frame, "1h"),
            "4h": source_metadata(h4_path, h4_frame, "4h"),
        },
    )
    db.add(run)
    db.flush()
    rows = build_signal_rows(
        result,
        replay_run_id=run.id,
        m5_frame=m5_frame,
        m15_frame=m15_frame,
    )
    db.add_all(rows)
    db.commit()
    return run, rows


def test_forward_metrics_use_trigger_close_and_report_partial_horizons():
    opens = pd.date_range("2026-01-01 00:00:00", periods=30, freq="5min", tz="UTC")
    closes = np.full(len(opens), 110.0)
    closes[0:3] = 100.0
    closes[3:15] = np.linspace(102.0, 110.0, 12)
    highs = closes + 1.0
    lows = closes - 1.0
    lows[3] = 99.0
    frame = pd.DataFrame(
        {
            "open": closes,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": 1.0,
        },
        index=opens,
    )
    signal = SimpleNamespace(
        timeframe="5m",
        data=SimpleNamespace(
            trigger_close_time=datetime(2026, 1, 1, 0, 15, tzinfo=UTC),
            trigger_close_price=100,
        ),
    )

    metrics = calculate_forward_metrics(signal, frame)
    prepared_metrics = calculate_forward_metrics(
        signal,
        prepare_forward_metric_source(frame, "5m"),
    )

    assert prepared_metrics == metrics
    assert metrics[0]["horizon_minutes"] == 60
    assert metrics[0]["complete"] is True
    assert metrics[0]["return_pct"] == pytest.approx(10.0)
    assert metrics[0]["mfe_pct"] == pytest.approx(11.0)
    assert metrics[0]["mae_pct"] == pytest.approx(-1.0)
    assert metrics[-1]["complete"] is False
    assert metrics[-1]["warning"]


def test_trade_plan_uses_future_native_candles_and_marks_ambiguous_wicks():
    opens = pd.date_range("2026-01-01 00:00:00", periods=5, freq="5min", tz="UTC")
    frame = pd.DataFrame(
        {
            "open": [100.0, 100.0, 101.0, 102.0, 103.0],
            "high": [110.0, 102.0, 106.0, 103.0, 104.0],
            "low": [90.0, 99.0, 100.0, 101.0, 102.0],
            "close": [100.0, 101.0, 105.0, 102.0, 103.0],
            "volume": 1.0,
        },
        index=opens,
    )
    trigger_close = opens[0].to_pydatetime() + timedelta(minutes=5)

    take_profit = evaluate_long_trade(
        frame,
        "5m",
        trigger_close=trigger_close,
        take_profit_price=Decimal("105"),
        stop_loss_price=Decimal("95"),
    )

    assert take_profit.exit_reason == TRADE_EXIT_TAKE_PROFIT
    assert take_profit.duration_minutes == 10
    assert take_profit.exit_at == opens[2].to_pydatetime() + timedelta(minutes=5)

    ambiguous = evaluate_long_trade(
        frame,
        "5m",
        trigger_close=trigger_close,
        take_profit_price=Decimal("101"),
        stop_loss_price=Decimal("99"),
    )

    assert ambiguous.exit_reason == TRADE_EXIT_BOTH_SAME_CANDLE
    assert ambiguous.duration_minutes == 5
    assert ambiguous.warning is not None

    stop_loss = evaluate_long_trade(
        frame,
        "5m",
        trigger_close=trigger_close,
        take_profit_price=Decimal("107"),
        stop_loss_price=Decimal("99"),
    )
    assert stop_loss.exit_reason == TRADE_EXIT_STOP_LOSS
    assert stop_loss.duration_minutes == 5

    still_open = evaluate_long_trade(
        frame,
        "5m",
        trigger_close=trigger_close,
        take_profit_price=Decimal("200"),
        stop_loss_price=Decimal("1"),
    )
    assert still_open.exit_reason == TRADE_EXIT_OPEN
    assert still_open.exit_at is None

    no_data = evaluate_long_trade(
        frame.iloc[:1],
        "5m",
        trigger_close=trigger_close,
        take_profit_price=Decimal("105"),
        stop_loss_price=Decimal("95"),
    )
    assert no_data.exit_reason == TRADE_EXIT_NO_DATA


def test_signal_rows_prepare_metric_sources_once_and_report_progress(
    tmp_path,
    monkeypatch,
):
    m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)
    result = run_btc_alert_replay(
        m5_path,
        m15_path,
        h4_path,
        start_utc7=datetime(2026, 8, 24, 16, 40),
        end_utc7=datetime(2026, 8, 24, 17, 10),
        write_output=False,
    )
    m5_frame = load_ohlcv_csv(m5_path, "5m")
    m15_frame = load_ohlcv_csv(m15_path, "15m")
    prepared_timeframes: list[str] = []

    from app.backtest import signal_replay_persistence

    real_prepare = signal_replay_persistence.prepare_forward_metric_source

    def tracked_prepare(frame, timeframe):
        prepared_timeframes.append(timeframe)
        return real_prepare(frame, timeframe)

    monkeypatch.setattr(
        signal_replay_persistence,
        "prepare_forward_metric_source",
        tracked_prepare,
    )
    progress: list[tuple[int, int]] = []
    rows = build_signal_rows(
        result,
        replay_run_id=1,
        m5_frame=m5_frame,
        m15_frame=m15_frame,
        on_progress=lambda completed, total: progress.append((completed, total)),
    )

    assert prepared_timeframes == ["5m", "15m"]
    assert progress[0] == (1, len(rows))
    assert progress[-1] == (len(rows), len(rows))


def test_replay_availability_uses_common_canonical_range(tmp_path, monkeypatch):
    m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)
    h1_path = h4_path.with_name("BTCUSDT_1h.csv")
    monkeypatch.setattr(
        signal_replay_service,
        "_default_paths",
        lambda: (m5_path, m15_path, h1_path, h4_path),
    )

    availability = SignalReplayService().get_availability()

    assert availability["ready"] is True
    assert {source["timeframe"] for source in availability["sources"]} == {
        "5m",
        "15m",
        "1h",
        "4h",
    }
    starts = [
        datetime.fromisoformat(source["available_start"])
        for source in availability["sources"]
    ]
    ends = [
        datetime.fromisoformat(source["available_end"])
        for source in availability["sources"]
    ]
    assert datetime.fromisoformat(availability["common_start_at"]) == max(starts)
    assert datetime.fromisoformat(availability["common_end_at"]) == min(ends)


def test_replay_start_rejects_range_outside_available_data(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    service = SignalReplayService()
    monkeypatch.setattr(
        service,
        "get_availability",
        lambda: {
            "ready": True,
            "common_start_at": "2026-01-01T00:00:00+00:00",
            "common_end_at": "2026-01-31T23:59:59+00:00",
            "sources": [],
        },
    )
    try:
        with pytest.raises(ValueError, match="available data range"):
            asyncio.run(service.start_run("2025-12-01", "2026-01-15", db))
        assert db.query(SignalReplayRun).count() == 0
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_replay_start_defaults_to_common_range(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    service = SignalReplayService()
    monkeypatch.setattr(
        service,
        "get_availability",
        lambda: {
            "ready": True,
            "common_start_at": "2026-01-01T00:00:00+00:00",
            "common_end_at": "2026-01-31T23:59:59+00:00",
            "sources": [],
        },
    )
    submitted: dict[str, object] = {}

    def fake_submit(job_id, worker, **kwargs):
        submitted.update({"job_id": job_id, "worker": worker, **kwargs})
        return SimpleNamespace()

    monkeypatch.setattr(signal_replay_service.executor, "submit_backtest", fake_submit)
    try:
        run_id = asyncio.run(service.start_run(None, None, db))
        run = db.query(SignalReplayRun).filter_by(id=run_id).one()

        assert run.requested_start_at == datetime(2026, 1, 1)
        assert run.requested_end_at == datetime(2026, 1, 31, 23, 59, 59)
        assert submitted["job_id"] == run_id
        assert submitted["run_id"] == run_id
    finally:
        signal_replay_service.executor.cleanup_job(1)
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_reconcile_orphaned_replay_runs(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    run = SignalReplayRun(
        status="running",
        definition_version="btc-rsi-cross-v1",
        symbol="BTC/USDT",
    )
    db.add(run)
    db.commit()
    monkeypatch.setattr(
        signal_replay_service.executor,
        "get_progress_queue",
        lambda _run_id: None,
    )
    try:
        SignalReplayService().reconcile_orphaned_runs(db)
        db.refresh(run)

        assert run.status == "failed"
        assert "interrupted" in run.error_message
        assert run.completed_at is not None
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_persistence_keeps_exact_card_and_structured_snapshot(tmp_path):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    try:
        _run, rows = _seed_replay(tmp_path, db)
        assert len(rows) == 2
        assert all(row.telegram_card.startswith("🟢 BTC RSI") for row in rows)
        assert rows[0].snapshot["decision"]["event_id"] == rows[0].event_id
        assert rows[0].snapshot["snapshot_version"] == "btc-rsi-cross-v1"
        assert rows[0].review.quality == "UNREVIEWED"
        assert {metric.horizon_minutes for metric in rows[0].forward_metrics} == {60, 240, 720, 1440}

        duplicate_values = {
            column.name: getattr(rows[0], column.name)
            for column in SignalReplaySignal.__table__.columns
            if column.name != "id"
        }
        with pytest.raises(IntegrityError):
            db.execute(insert(SignalReplaySignal).values(duplicate_values))
            db.commit()
        db.rollback()

        second_run = SignalReplayRun(
            status="completed",
            definition_version="btc-rsi-cross-v1",
            symbol="BTC/USDT",
            source_metadata={},
        )
        db.add(second_run)
        db.commit()
        assert second_run.id != _run.id
        assert db.query(SignalReplayRun).count() == 2
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_chart_future_is_locked_until_quality_review():
    opens = pd.date_range("2026-01-01 00:00:00", periods=100, freq="5min", tz="UTC")
    values = np.linspace(100.0, 110.0, len(opens))
    frame = pd.DataFrame(
        {
            "open": values,
            "high": values + 1.0,
            "low": values - 1.0,
            "close": values,
            "volume": 1.0,
        },
        index=opens,
    )
    trigger = opens[20] + timedelta(minutes=5)

    locked, locked_meta = chart_candles(frame, "5m", trigger_close=trigger, after=5, allow_future=False)
    unlocked, unlocked_meta = chart_candles(frame, "5m", trigger_close=trigger, after=5, allow_future=True)

    assert locked[-1]["is_trigger"] is True
    assert len(unlocked) == len(locked) + 5
    assert locked_meta["future_allowed"] is False
    assert unlocked_meta["future_allowed"] is True


def test_chart_exposes_full_indicator_set_and_anchors_higher_timeframe():
    opens = pd.date_range(
        "2026-01-01 00:00:00",
        periods=350,
        freq="1h",
        tz="UTC",
    )
    values = np.linspace(100.0, 180.0, len(opens)) + np.sin(np.arange(len(opens)))
    frame = pd.DataFrame(
        {
            "open": values,
            "high": values + 1.0,
            "low": values - 1.0,
            "close": values,
            "volume": 1.0,
        },
        index=opens,
    )
    anchor_time = (opens[300] + timedelta(hours=1)).to_pydatetime()
    signal_time = anchor_time + timedelta(minutes=30)

    candles, metadata = chart_candles(
        frame,
        "1h",
        trigger_close=signal_time,
        allow_future=False,
    )

    anchor = next(candle for candle in candles if candle["is_trigger"])
    assert anchor["time"] == anchor_time.isoformat()
    assert metadata["signal_time"] == signal_time.isoformat()
    assert metadata["anchor_time"] == anchor_time.isoformat()
    for indicator in ("ema21", "ema200", "rsi21", "rsi_ema9", "rsi_wma45"):
        assert anchor[indicator] is not None


def test_default_unlocked_chart_loads_two_thousand_future_candles():
    periods = CHART_CHUNK_CANDLES + 400
    opens = pd.date_range(
        "2026-01-01 00:00:00",
        periods=periods,
        freq="5min",
        tz="UTC",
    )
    values = np.linspace(100.0, 120.0, len(opens))
    frame = pd.DataFrame(
        {
            "open": values,
            "high": values + 1.0,
            "low": values - 1.0,
            "close": values,
            "volume": 1.0,
        },
        index=opens,
    )
    trigger = opens[300] + timedelta(minutes=5)

    candles, metadata = chart_window_from_frame(
        frame,
        "5m",
        trigger_close=trigger,
        start_at=None,
        end_at=None,
        allow_future=True,
    )

    trigger_index = next(
        index for index, candle in enumerate(candles) if candle["is_trigger"]
    )
    assert CHART_CHUNK_CANDLES == 2_000
    assert len(candles) - trigger_index - 1 == CHART_CHUNK_CANDLES
    assert metadata["requested_end"] == (
        trigger + timedelta(minutes=5 * CHART_CHUNK_CANDLES)
    ).isoformat()


def test_chart_range_reports_csv_boundaries():
    opens = pd.date_range("2026-01-01 00:00:00", periods=100, freq="5min", tz="UTC")
    values = np.linspace(100.0, 110.0, len(opens))
    frame = pd.DataFrame(
        {
            "open": values,
            "high": values + 1.0,
            "low": values - 1.0,
            "close": values,
            "volume": 1.0,
        },
        index=opens,
    )
    trigger = opens[20] + timedelta(minutes=5)

    _candles, metadata = chart_window_from_frame(
        frame,
        "5m",
        trigger_close=trigger,
        start_at=trigger - timedelta(days=1),
        end_at=trigger + timedelta(days=1),
        allow_future=True,
    )

    assert "starts after" in metadata["warning"]
    assert "ends before" in metadata["warning"]


def test_signal_api_filters_persists_review_and_reloads_chart(tmp_path):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)

    def override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[signal_replays.get_db] = override_get_db
    client = TestClient(app)
    db = session_factory()
    try:
        _run, rows = _seed_replay(tmp_path, db)
        m5_id = next(row.id for row in rows if row.timeframe == "5m")
        m15_id = next(row.id for row in rows if row.timeframe == "15m")

        filtered = client.get("/api/signal-replays/signals", params={"timeframe": "5m", "page": 1, "limit": 10})
        assert filtered.status_code == 200
        assert filtered.json()["total"] == 1
        assert filtered.json()["signals"][0]["quality"] == SignalQuality.UNREVIEWED.value

        locked = client.get(f"/api/signal-replays/signals/{m5_id}/chart")
        assert locked.status_code == 200
        assert locked.json()["future_allowed"] is False
        assert "locked" in locked.json()["warning"]

        locked_h1 = client.get(
            f"/api/signal-replays/signals/{m5_id}/chart",
            params={"timeframe": "1h"},
        )
        assert locked_h1.status_code == 200
        assert locked_h1.json()["timeframe"] == "1h"
        assert locked_h1.json()["future_allowed"] is False
        assert locked_h1.json()["anchor_time"] <= locked_h1.json()["signal_time"]
        assert sum(candle["is_trigger"] for candle in locked_h1.json()["candles"]) == 1

        source_path = Path(_run.source_metadata["5m"]["path"])
        source_frame = pd.read_csv(source_path)
        m5_signal = next(row for row in rows if row.id == m5_id)
        entry = Decimal(m5_signal.trigger_close_price)
        future_row = source_frame.tail(1).copy()
        future_row.loc[:, "timestamp"] = (
            pd.Timestamp(source_frame.iloc[-1]["timestamp"]) + timedelta(minutes=5)
        ).strftime("%Y-%m-%d %H:%M:%S")
        future_row.loc[:, "open"] = float(entry)
        future_row.loc[:, "high"] = float(entry + Decimal("10"))
        future_row.loc[:, "low"] = float(entry)
        future_row.loc[:, "close"] = float(entry + Decimal("1"))
        source_frame = pd.concat([source_frame, future_row], ignore_index=True)
        source_frame.to_csv(source_path, index=False)

        plan_before_quality = client.patch(
            f"/api/signal-replays/signals/{m5_id}/review",
            json={
                "take_profit_price": str(entry + Decimal("5")),
                "stop_loss_price": str(entry - Decimal("5")),
            },
        )
        assert plan_before_quality.status_code == 200
        staged_plan = plan_before_quality.json()
        assert staged_plan["quality"] == SignalQuality.UNREVIEWED.value
        assert staged_plan["entry_price"] == m5_signal.trigger_close_price
        assert staged_plan["take_profit_price"] == str(entry + Decimal("5"))
        assert staged_plan["stop_loss_price"] == str(entry - Decimal("5"))
        assert staged_plan["exit_reason"] is None
        assert staged_plan["evaluated_at"] is None
        assert staged_plan["human_outcome"] == SignalHumanOutcome.UNSET.value

        review = client.patch(
            f"/api/signal-replays/signals/{m5_id}/review",
            json={"quality": SignalQuality.GOOD.value},
        )
        assert review.status_code == 200
        plan_review = review.json()
        assert plan_review["quality"] == SignalQuality.GOOD.value
        assert plan_review["exit_reason"] == TRADE_EXIT_TAKE_PROFIT
        assert plan_review["duration_minutes"] == 5

        unlocked = client.get(f"/api/signal-replays/signals/{m5_id}/chart")
        assert unlocked.status_code == 200
        assert unlocked.json()["future_allowed"] is True
        assert {"ema21", "ema200", "rsi21", "rsi_ema9", "rsi_wma45"}.issubset(
            unlocked.json()["candles"][-1]
        )

        h4_chart = client.get(
            f"/api/signal-replays/signals/{m5_id}/chart",
            params={"timeframe": "4h"},
        )
        assert h4_chart.status_code == 200
        assert h4_chart.json()["timeframe"] == "4h"
        assert h4_chart.json()["anchor_time"] <= h4_chart.json()["signal_time"]

        invalid_chart = client.get(
            f"/api/signal-replays/signals/{m5_id}/chart",
            params={"timeframe": "1d"},
        )
        assert invalid_chart.status_code == 400
        assert "5m, 15m, 1h, or 4h" in invalid_chart.json()["detail"]

        source_frame = pd.read_csv(source_path)
        extra_row = source_frame.tail(1).copy()
        extra_row.loc[:, "timestamp"] = (
            pd.Timestamp(source_frame.iloc[-1]["timestamp"]) + timedelta(minutes=5)
        ).strftime("%Y-%m-%d %H:%M:%S")
        source_frame = pd.concat([source_frame, extra_row], ignore_index=True)
        source_frame.to_csv(source_path, index=False)
        changed_source = client.get(f"/api/signal-replays/signals/{m5_id}/chart")
        assert changed_source.status_code == 200
        assert "row count differs" in changed_source.json()["warning"]

        outcome = client.patch(
            f"/api/signal-replays/signals/{m5_id}/review",
            json={"human_outcome": SignalHumanOutcome.WIN.value, "note": "clean continuation"},
        )
        assert outcome.status_code == 200
        assert outcome.json()["human_outcome"] == SignalHumanOutcome.WIN.value
        assert outcome.json()["note"] == "clean continuation"

        good = client.get("/api/signal-replays/signals", params={"quality": "GOOD"})
        assert good.status_code == 200
        assert good.json()["total"] == 1
        assert good.json()["signals"][0]["id"] == m5_id

        detail = client.get(f"/api/signal-replays/signals/{m5_id}")
        assert detail.status_code == 200
        assert detail.json()["review"]["human_outcome"] == SignalHumanOutcome.WIN.value
        assert detail.json()["telegram_card"] == next(row.telegram_card for row in rows if row.id == m5_id)
        assert client.get(f"/api/signal-replays/signals/{m15_id}").json()["review"]["human_outcome"] == SignalHumanOutcome.UNSET.value

        failed_run = SignalReplayRun(
            status="failed",
            definition_version="btc-rsi-cross-v1",
            symbol="BTC/USDT",
            error_message="CSV unavailable",
        )
        db.add(failed_run)
        db.commit()
        progress = client.get(f"/api/signal-replays/runs/{failed_run.id}/progress")
        assert progress.status_code == 200
        assert "event: error" in progress.text
        assert "CSV unavailable" in progress.text
    finally:
        app.dependency_overrides.pop(signal_replays.get_db, None)
        db.close()
        Base.metadata.drop_all(bind=engine)


def test_outcome_cannot_be_saved_before_quality(tmp_path):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    db = sessionmaker(bind=engine)()
    try:
        _run, rows = _seed_replay(tmp_path, db)
        service = SignalReplayService()
        try:
            service.update_review(rows[0].id, SignalReviewUpdate(human_outcome=SignalHumanOutcome.WIN), db)
        except ValueError as exc:
            assert "quality" in str(exc)
        else:
            raise AssertionError("an outcome must require a quality label")
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

"""Tests for the offline BTC RSI alert replay and Markdown audit log."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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

import app.backtest.signal_replay as signal_replay
import app.backtest.signal_replay_preparation as replay_preparation
from app.backtest.signal_replay import (
    SignalReplayInputError,
    render_replay_markdown,
    run_btc_alert_replay,
)
from app.backtest.signal_replay_models import ReplayTriggerEvent
from app.backtest.signal_replay_preparation import ReplayPreparationCache
from app.trading.strategy.btc_rsi_cross_alert.evaluator import TRIGGER_DURATION_BY_TIMEFRAME
from app.trading.strategy.btc_rsi_cross_alert.m5_checker import prepare_m5_cross_input
from app.trading.strategy.btc_rsi_cross_alert.m15_checker import prepare_m15_cross_input
from app.trading.strategy.btc_rsi_cross_alert.models import BtcRsiCrossDecision
from app.trading.strategy.core_v2_1.indicators import wma

STORAGE_SHIFT = timedelta(hours=7)


def _write_ohlcv_csv(
    path,
    close_times: list[datetime],
    closes: list[float],
    step: timedelta,
) -> None:
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
    if "4h" in path.name or path.stem == "h4":
        h1_path = (
            path.with_name(path.name.replace("4h", "1h"))
            if "4h" in path.name
            else path.with_name("h1.csv")
        )
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


class TestBtcAlertReplay:
    def test_replays_both_timeframes_with_full_telegram_card(self, tmp_path):
        m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)
        output_path = tmp_path / "replay.md"
        generated_at = datetime(2026, 8, 28, 18, 30, tzinfo=UTC)

        result = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 40),
            end_utc7=datetime(2026, 8, 24, 17, 10),
            output_path=output_path,
            generated_at_utc7=generated_at,
        )

        assert {signal.timeframe for signal in result.signals} == {"5m", "15m"}
        assert [signal.sequence for signal in result.signals] == [1, 2]
        assert result.signals[0].data.trigger_close_time < result.signals[1].data.trigger_close_time

        body = output_path.read_text(encoding="utf-8")
        assert "# BTC RSI Cross Alert — Historical Replay" in body
        assert "Data window: 2026-08-24 16:40:00 UTC+7 → 2026-08-24 17:10:00 UTC+7" in body
        assert "Generated: 2026-08-29 01:30:00 UTC+7" in body
        assert "Automated win rate: NOT CALCULATED" in body
        assert "Manual review: UNREVIEWED" in body
        assert "Chart result: [ ] WIN   [ ] LOSS   [ ] SKIP" in body

        m5_card = next(signal.telegram_card for signal in result.signals if signal.timeframe == "5m")
        assert "🟢 BTC RSI BULLISH ALIGNMENT" in m5_card
        assert "Timeframe: 5m" in m5_card
        assert "Candle close: 2026-08-24 16:45:00 UTC+7" in m5_card
        assert "BTC close:" in m5_card
        assert "M5 EMA21(price):" in m5_card
        assert "M5 close > EMA21(price):" in m5_card
        assert "Current M5 RSI21:" in m5_card
        assert "Current M5 EMA9(RSI21):" in m5_card
        assert "Current M5 WMA45(RSI21):" in m5_card
        assert "M5 RSI alignment:" in m5_card
        assert "M5 EMA9(RSI21) - WMA45(RSI21):" in m5_card
        assert "M5 WMA45(RSI21) > 45.00:" in m5_card
        assert "M5 RSI21 < 60.00:" in m5_card
        assert "H1 close:" in m5_card
        assert "H1 EMA21(price):" in m5_card
        assert "H1 close > EMA21(price):" in m5_card
        assert "H4 close:" in m5_card
        assert "H4 EMA21(price):" in m5_card
        assert "H4 close > EMA21(price):" in m5_card
        assert "Duplicate check: NEW event ✅" in m5_card
        assert "Event:" in m5_card

        m15_card = next(signal.telegram_card for signal in result.signals if signal.timeframe == "15m")
        assert "🟢 BTC RSI BULLISH CROSS" in m15_card
        assert "Timeframe: 15m" in m15_card
        assert "Candle close: 2026-08-24 17:00:00 UTC+7" in m15_card
        assert "BTC close:" in m15_card
        assert "M15 EMA21(price):" in m15_card
        assert "M15 close > EMA21(price):" in m15_card
        assert "Previous M15 EMA9(RSI21):" in m15_card
        assert "Previous M15 WMA45(RSI21):" in m15_card
        assert "Fresh bullish cross:" in m15_card
        assert "Current M15 RSI21:" in m15_card
        assert "Current M15 EMA9(RSI21):" in m15_card
        assert "Current M15 WMA45(RSI21):" in m15_card
        assert "H1 close:" in m15_card
        assert "H1 EMA21(price):" in m15_card
        assert "H1 close > EMA21(price):" in m15_card
        assert "H4 close:" in m15_card
        assert "H4 EMA21(price):" in m15_card
        assert "H4 close > EMA21(price):" in m15_card
        assert "Duplicate check: NEW event ✅" in m15_card
        assert "Event:" in m15_card
        assert "M15 close > EMA21(price):" in m15_card

    def test_split_reports_contain_only_their_timeframe_cards(self, tmp_path):
        m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)
        m5_output = tmp_path / "replay_m5.md"
        m15_output = tmp_path / "replay_m15.md"

        result = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 40),
            end_utc7=datetime(2026, 8, 24, 17, 10),
            output_m5_path=m5_output,
            output_m15_path=m15_output,
            generated_at_utc7=datetime(2026, 8, 28, 18, 30, tzinfo=UTC),
        )

        assert result.output_path is None
        assert result.output_paths == (m5_output, m15_output)
        m5_body = m5_output.read_text(encoding="utf-8")
        m15_body = m15_output.read_text(encoding="utf-8")

        assert "Timeframe: 5m" in m5_body
        assert "5m signals: 1" in m5_body
        assert "Signal 0001 — CONFIRMED — M5" in m5_body
        assert "🟢 BTC RSI BULLISH ALIGNMENT" in m5_body
        assert "BTC RSI BULLISH CROSS" not in m5_body
        assert "M15 close > EMA21(price):" not in m5_body

        assert "Timeframe: 15m" in m15_body
        assert "15m signals: 1" in m15_body
        assert "Signal 0001 — CONFIRMED — M15" in m15_body
        assert "🟢 BTC RSI BULLISH CROSS" in m15_body
        assert "BTC RSI BULLISH ALIGNMENT" not in m15_body
        assert "M5 close > EMA21(price):" not in m15_body

        for signal in result.signals:
            body = m5_body if signal.timeframe == "5m" else m15_body
            assert signal.telegram_card in body

    def test_split_report_paths_must_be_provided_together(self, tmp_path):
        m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)

        with pytest.raises(ValueError, match="must be provided together"):
            run_btc_alert_replay(
                m5_path,
                m15_path,
                h4_path,
                output_m5_path=tmp_path / "replay_m5.md",
            )

    def test_default_output_is_split_by_timeframe(self, tmp_path, monkeypatch):
        m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)
        monkeypatch.setattr(signal_replay, "DEFAULT_REPORT_DIR", tmp_path / "report")

        result = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 40),
            end_utc7=datetime(2026, 8, 24, 17, 10),
            generated_at_utc7=datetime(2026, 8, 28, 18, 30, tzinfo=UTC),
        )

        assert result.output_paths == (
            tmp_path / "report" / "signal_replay_2026-08-24_2026-08-24_m5.md",
            tmp_path / "report" / "signal_replay_2026-08-24_2026-08-24_m15.md",
        )
        assert all(path.exists() for path in result.output_paths)

    def test_naive_csv_open_is_shifted_once_and_rendered_in_utc_plus_7(self, tmp_path):
        m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)
        output_path = tmp_path / "replay.md"
        result = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 40),
            end_utc7=datetime(2026, 8, 24, 17, 10),
            output_path=output_path,
            generated_at_utc7=datetime(2026, 8, 28, 0, tzinfo=UTC),
        )

        assert result.signals[0].data.trigger_close_time == datetime(
            2026, 8, 24, 9, 45, tzinfo=UTC
        )
        assert "UTC+7" in output_path.read_text(encoding="utf-8")
        assert "2026-08-24 16:45:00 UTC+7" in output_path.read_text(encoding="utf-8")

    def test_indicator_warmup_is_kept_before_requested_start(self, tmp_path):
        m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)
        result = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 45),
            end_utc7=datetime(2026, 8, 24, 16, 45),
            output_path=tmp_path / "warmup.md",
            generated_at_utc7=datetime(2026, 8, 28, tzinfo=UTC),
        )

        assert [signal.timeframe for signal in result.signals] == ["5m"]
        assert result.counts.m5_candidates == 1
        assert result.counts.m15_candidates == 1
        assert result.counts.m15_rejected == 1
        assert result.counts.m5_not_ready == 0

    def test_initial_warmup_events_are_skipped_from_evaluation(self, tmp_path, monkeypatch):
        close_times = [BASE.replace(hour=9, minute=minute) for minute in (0, 5)]
        m5_path = tmp_path / "m5.csv"
        m15_path = tmp_path / "m15.csv"
        h4_path = tmp_path / "h4.csv"
        _write_ohlcv_csv(m5_path, close_times, [100.0] * 2, timedelta(minutes=5))
        _write_ohlcv_csv(m15_path, [BASE.replace(hour=9, minute=5)], [100.0], timedelta(minutes=15))
        _write_ohlcv_csv(h4_path, [BASE.replace(hour=0)], [100.0], timedelta(hours=4))

        warmup_ready_at = datetime(2026, 8, 24, 9, 5, tzinfo=UTC)
        monkeypatch.setattr(
            ReplayPreparationCache,
            "warmup_ready_at_by_timeframe",
            property(lambda _cache: {"5m": warmup_ready_at, "15m": warmup_ready_at}),
        )

        def fake_prepare(event, *_frames):
            decision = BtcRsiCrossDecision(
                should_alert=True,
                event_id=f"{event.timeframe}-{event.close_time.isoformat()}",
                reason="TEST_ALERT",
            )
            return object(), decision, "READY"

        monkeypatch.setattr(signal_replay, "_prepare_and_evaluate", fake_prepare)
        monkeypatch.setattr(
            signal_replay,
            "_scan_event",
            lambda _event, _cache: (True, "READY"),
        )
        monkeypatch.setattr(
            signal_replay,
            "format_btc_rsi_cross_alert",
            lambda _data, event_id: f"Event: {event_id}",
        )

        output_path = tmp_path / "warmup-skip.md"
        result = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 0),
            end_utc7=datetime(2026, 8, 24, 16, 10),
            output_path=output_path,
            generated_at_utc7=datetime(2026, 8, 28, tzinfo=UTC),
        )

        assert len(result.signals) == 2
        assert result.counts.warmup_skipped == 1
        assert result.counts.m5_warmup_skipped == 1
        assert result.counts.m15_warmup_skipped == 0
        assert result.counts.not_ready == 0
        assert "Warmup candles skipped: 1" in output_path.read_text(encoding="utf-8")

    def test_precomputed_preparation_matches_existing_checker(self, tmp_path):
        m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)
        m5_frame = signal_replay._load_ohlcv_csv(m5_path, "5m")
        m15_frame = signal_replay._load_ohlcv_csv(m15_path, "15m")
        h1_frame = signal_replay._load_ohlcv_csv(
            h4_path.with_name(h4_path.name.replace("4h", "1h")), "1h"
        )
        h4_frame = signal_replay._load_ohlcv_csv(h4_path, "4h")
        observed_h1_closes = signal_replay._all_h1_close_times(h1_frame)
        observed_h4_closes = signal_replay._all_h4_close_times(h4_frame)
        cache = ReplayPreparationCache(
            m5_frame,
            m15_frame,
            h4_frame,
            h1_frame,
            history_ready_at=signal_replay.HISTORICAL_READY_AT,
            observed_h1_closes=observed_h1_closes,
            observed_h4_closes=observed_h4_closes,
        )
        result = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 40),
            end_utc7=datetime(2026, 8, 24, 17, 10),
            output_path=tmp_path / "parity.md",
            generated_at_utc7=datetime(2026, 8, 28, tzinfo=UTC),
        )

        for signal in result.signals:
            duration = TRIGGER_DURATION_BY_TIMEFRAME[signal.timeframe]
            event = ReplayTriggerEvent(
                timeframe=signal.timeframe,
                open_time=signal.data.trigger_close_time - duration,
                close_time=signal.data.trigger_close_time,
            )
            preparer = (
                prepare_m5_cross_input
                if signal.timeframe == "5m"
                else prepare_m15_cross_input
            )
            trigger_frame = m5_frame if signal.timeframe == "5m" else m15_frame
            slow = preparer(
                trigger_frame,
                h4_frame,
                h1_df=h1_frame,
                symbol="BTC/USDT",
                trigger_open_time=event.open_time,
                history_ready_at=signal_replay.HISTORICAL_READY_AT,
                observed_live_h1_closes=observed_h1_closes,
                observed_live_h4_closes=observed_h4_closes,
            )
            fast = cache.prepare(event, symbol="BTC/USDT")
            assert fast == slow

    def test_candidate_scan_never_drops_an_exact_signal(self, tmp_path):
        m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)
        m5_frame = signal_replay._load_ohlcv_csv(m5_path, "5m")
        m15_frame = signal_replay._load_ohlcv_csv(m15_path, "15m")
        h1_frame = signal_replay._load_ohlcv_csv(
            h4_path.with_name(h4_path.name.replace("4h", "1h")), "1h"
        )
        h4_frame = signal_replay._load_ohlcv_csv(h4_path, "4h")
        observed_h1_closes = signal_replay._all_h1_close_times(h1_frame)
        observed_h4_closes = signal_replay._all_h4_close_times(h4_frame)
        cache = ReplayPreparationCache(
            m5_frame,
            m15_frame,
            h4_frame,
            h1_frame,
            history_ready_at=signal_replay.HISTORICAL_READY_AT,
            observed_h1_closes=observed_h1_closes,
            observed_h4_closes=observed_h4_closes,
        )
        events = signal_replay._events_for_frame(m5_frame, "5m", None, None)
        events.extend(signal_replay._events_for_frame(m15_frame, "15m", None, None))

        exact_alerts = 0
        for event in events:
            data, decision, _reason = cache.prepare_and_evaluate(
                event, symbol="BTC/USDT"
            )
            if data is None or decision is None or not decision.should_alert:
                continue
            exact_alerts += 1
            is_candidate, scan_reason = cache.scan(event)
            assert is_candidate is True
            assert scan_reason == "READY"

        assert exact_alerts >= 2

    def test_vectorized_wma_stays_inside_candidate_scan_tolerance(self):
        rng = np.random.default_rng(20260828)
        values = pd.Series(
            [np.nan] * 21 + rng.uniform(0.0, 100.0, size=500).tolist(),
            dtype="float64",
        )
        locked = wma(values, replay_preparation.RSI_WMA_PERIOD).to_numpy()
        fast = replay_preparation._fast_wma(
            values.to_numpy(), replay_preparation.RSI_WMA_PERIOD
        )
        finite = np.isfinite(locked) & np.isfinite(fast)

        assert finite.any()
        assert np.max(np.abs(locked[finite] - fast[finite])) < (
            replay_preparation.PREFILTER_TOLERANCE
        )

    def test_future_rows_do_not_change_an_earlier_replay(self, tmp_path):
        m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)
        baseline_path = tmp_path / "baseline.md"
        baseline = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 40),
            end_utc7=datetime(2026, 8, 24, 17, 10),
            output_path=baseline_path,
            generated_at_utc7=datetime(2026, 8, 28, tzinfo=UTC),
        )

        def append_future(path, timestamp, close):
            frame = pd.read_csv(path)
            frame.loc[len(frame)] = [timestamp, close, close, close, close, 1.0]
            frame.to_csv(path, index=False)

        append_future(m5_path, "2026-08-25 12:00:00", 999999.0)
        append_future(m15_path, "2026-08-25 12:00:00", 999999.0)
        append_future(h4_path, "2026-08-25 12:00:00", 999999.0)

        future_path = tmp_path / "future.md"
        future = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 40),
            end_utc7=datetime(2026, 8, 24, 17, 10),
            output_path=future_path,
            generated_at_utc7=datetime(2026, 8, 28, tzinfo=UTC),
        )

        assert [signal.telegram_card for signal in baseline.signals] == [
            signal.telegram_card for signal in future.signals
        ]

    def test_m5_cooldown_suppresses_until_one_hour(self, tmp_path, monkeypatch):
        close_times = [
            BASE.replace(hour=9, minute=minute) for minute in (0, 5, 10, 15, 55)
        ]
        close_times.append(BASE.replace(hour=10))
        m5_path = tmp_path / "m5.csv"
        m15_path = tmp_path / "m15.csv"
        h4_path = tmp_path / "h4.csv"
        _write_ohlcv_csv(m5_path, close_times, [100.0] * len(close_times), timedelta(minutes=5))
        _write_ohlcv_csv(m15_path, [BASE.replace(hour=1)], [100.0], timedelta(minutes=15))
        _write_ohlcv_csv(h4_path, [BASE.replace(hour=0)], [100.0], timedelta(hours=4))

        def fake_prepare(event, *_frames):
            decision = BtcRsiCrossDecision(
                should_alert=True,
                event_id=f"event-{(event.close_time - BASE) // timedelta(minutes=1)}",
                reason="TEST_ALERT",
            )
            return object(), decision, "READY"

        monkeypatch.setattr(signal_replay, "_prepare_and_evaluate", fake_prepare)
        monkeypatch.setattr(
            signal_replay,
            "_scan_event",
            lambda _event, _cache: (True, "READY"),
        )
        monkeypatch.setattr(
            signal_replay,
            "format_btc_rsi_cross_alert",
            lambda _data, event_id: f"Event: {event_id}",
        )

        result = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 0),
            end_utc7=datetime(2026, 8, 24, 17, 0),
            output_path=tmp_path / "cooldown.md",
            generated_at_utc7=datetime(2026, 8, 28, tzinfo=UTC),
        )

        assert len(result.signals) == 2
        assert result.counts.m5_cooldown_suppressed == 4
        assert [signal.decision.event_id for signal in result.signals] == ["event-540", "event-600"]

    def test_m15_cooldown_suppresses_until_one_hour(self, tmp_path, monkeypatch):
        close_times = [
            BASE.replace(hour=9, minute=minute) for minute in (0, 15, 30, 45)
        ]
        close_times.append(BASE.replace(hour=10))
        m5_path = tmp_path / "m5.csv"
        m15_path = tmp_path / "m15.csv"
        h4_path = tmp_path / "h4.csv"
        _write_ohlcv_csv(
            m5_path,
            [BASE.replace(hour=1)],
            [100.0],
            timedelta(minutes=5),
        )
        _write_ohlcv_csv(
            m15_path,
            close_times,
            [100.0] * len(close_times),
            timedelta(minutes=15),
        )
        _write_ohlcv_csv(h4_path, [BASE.replace(hour=0)], [100.0], timedelta(hours=4))

        def fake_prepare(event, *_frames):
            decision = BtcRsiCrossDecision(
                should_alert=True,
                event_id=(
                    f"event-{event.timeframe}-"
                    f"{(event.close_time - BASE) // timedelta(minutes=1)}"
                ),
                reason="TEST_ALERT",
            )
            return object(), decision, "READY"

        monkeypatch.setattr(signal_replay, "_prepare_and_evaluate", fake_prepare)
        monkeypatch.setattr(
            signal_replay,
            "_scan_event",
            lambda _event, _cache: (True, "READY"),
        )
        monkeypatch.setattr(
            signal_replay,
            "format_btc_rsi_cross_alert",
            lambda _data, event_id: f"Event: {event_id}",
        )

        output_path = tmp_path / "m15-cooldown.md"
        result = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 0),
            end_utc7=datetime(2026, 8, 24, 17, 0),
            output_path=output_path,
            generated_at_utc7=datetime(2026, 8, 28, tzinfo=UTC),
        )

        assert len(result.signals) == 2
        assert result.counts.m5_cooldown_suppressed == 0
        assert result.counts.m15_cooldown_suppressed == 3
        assert [signal.decision.event_id for signal in result.signals] == [
            "event-15m-540",
            "event-15m-600",
        ]
        assert "M15 cooldown suppressed: 3" in output_path.read_text(encoding="utf-8")

    def test_duplicate_event_ids_are_suppressed_before_cooldown(self, tmp_path, monkeypatch):
        close_times = [BASE.replace(hour=9, minute=minute) for minute in (0, 5)]
        m5_path = tmp_path / "m5.csv"
        m15_path = tmp_path / "m15.csv"
        h4_path = tmp_path / "h4.csv"
        _write_ohlcv_csv(m5_path, close_times, [100.0] * 2, timedelta(minutes=5))
        _write_ohlcv_csv(m15_path, [BASE.replace(hour=1)], [100.0], timedelta(minutes=15))
        _write_ohlcv_csv(h4_path, [BASE.replace(hour=0)], [100.0], timedelta(hours=4))

        def fake_prepare(_event, *_frames):
            decision = BtcRsiCrossDecision(
                should_alert=True,
                event_id="same-event",
                reason="TEST_ALERT",
            )
            return object(), decision, "READY"

        monkeypatch.setattr(signal_replay, "_prepare_and_evaluate", fake_prepare)
        monkeypatch.setattr(
            signal_replay,
            "_scan_event",
            lambda _event, _cache: (True, "READY"),
        )
        monkeypatch.setattr(
            signal_replay,
            "format_btc_rsi_cross_alert",
            lambda _data, event_id: f"Event: {event_id}",
        )

        result = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            start_utc7=datetime(2026, 8, 24, 16, 0),
            end_utc7=datetime(2026, 8, 24, 16, 10),
            output_path=tmp_path / "duplicate.md",
            generated_at_utc7=datetime(2026, 8, 28, tzinfo=UTC),
        )

        assert len(result.signals) == 1
        assert result.counts.duplicate_suppressed == 1
        assert result.counts.m5_cooldown_suppressed == 0

    def test_rejected_events_skip_full_domain_evaluation(self, tmp_path, monkeypatch):
        m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)
        evaluated = 0

        def fail_if_evaluated(_event, _cache):
            nonlocal evaluated
            evaluated += 1
            raise AssertionError("rejected candles must not build domain inputs")

        monkeypatch.setattr(
            signal_replay,
            "_scan_event",
            lambda _event, _cache: (False, "READY"),
        )
        monkeypatch.setattr(signal_replay, "_prepare_and_evaluate", fail_if_evaluated)

        result = run_btc_alert_replay(
            m5_path,
            m15_path,
            h4_path,
            output_path=tmp_path / "prefilter.md",
            generated_at_utc7=datetime(2026, 8, 28, tzinfo=UTC),
        )

        assert evaluated == 0
        assert result.signals == ()
        assert (
            result.counts.rejected + result.counts.warmup_skipped
            == result.counts.candidates
        )

    def test_mixed_naive_and_aware_csv_timestamps_keep_their_instants(self, tmp_path):
        path = tmp_path / "mixed.csv"
        pd.DataFrame(
            {
                "timestamp": [
                    "2026-08-24 16:00:00",
                    "2026-08-24T09:05:00+00:00",
                ],
                "open": [100.0, 101.0],
                "high": [100.0, 101.0],
                "low": [100.0, 101.0],
                "close": [100.0, 101.0],
                "volume": [1.0, 1.0],
            }
        ).to_csv(path, index=False)

        frame = signal_replay._load_ohlcv_csv(path, "5m")

        assert list(frame.index.to_pydatetime()) == [
            datetime(2026, 8, 24, 9, 0, tzinfo=UTC),
            datetime(2026, 8, 24, 9, 5, tzinfo=UTC),
        ]

    def test_invalid_csv_schema_fails_before_writing_output(self, tmp_path):
        bad_path = tmp_path / "bad.csv"
        pd.DataFrame({"timestamp": ["2026-08-24 16:00:00"], "close": [100.0]}).to_csv(
            bad_path, index=False
        )
        valid = tmp_path / "valid.csv"
        _write_ohlcv_csv(valid, [BASE], [100.0], timedelta(minutes=5))

        with pytest.raises(SignalReplayInputError, match="missing columns"):
            run_btc_alert_replay(
                bad_path,
                valid,
                valid,
                output_path=tmp_path / "should-not-exist.md",
            )

        assert not (tmp_path / "should-not-exist.md").exists()


def test_render_replay_markdown_is_repeatable_for_fixed_generation_time(tmp_path):
    m5_path, m15_path, h4_path = _write_qualifying_csvs(tmp_path)
    result = run_btc_alert_replay(
        m5_path,
        m15_path,
        h4_path,
        start_utc7=datetime(2026, 8, 24, 16, 40),
        end_utc7=datetime(2026, 8, 24, 17, 10),
        output_path=tmp_path / "replay.md",
        generated_at_utc7=datetime(2026, 8, 28, tzinfo=UTC),
    )
    generated_at = datetime(2026, 8, 28, 18, 30, tzinfo=UTC)

    assert render_replay_markdown(result, generated_at=generated_at) == render_replay_markdown(
        result, generated_at=generated_at
    )
